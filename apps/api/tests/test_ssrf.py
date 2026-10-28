import httpx
import pytest

from app.services import safe_fetch
from app.services.safe_fetch import FetchBlocked, is_public_ip, safe_get, validate_url

BLOCKED_URLS = [
    "http://localhost/admin",
    "http://127.0.0.1/",
    "http://127.1/",
    "http://2130706433/",  # decimal 127.0.0.1
    "http://0x7f000001/",  # hex 127.0.0.1
    "http://0.0.0.0/",
    "http://10.0.0.5/",
    "http://172.16.3.4/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://100.64.0.1/",  # CGNAT
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[fd00::1]/",
    "file:///etc/passwd",
    "gopher://example.com/",
    "ftp://example.com/",
    "http://user:pass@example.com/",
    "http://example.com:22/",
    "http://printer.local/",
    "javascript:alert(1)",
]


@pytest.mark.parametrize("url", BLOCKED_URLS)
async def test_ssrf_corpus_blocked(url: str) -> None:
    with pytest.raises(FetchBlocked):
        await validate_url(url)


def test_public_ip_classification() -> None:
    assert is_public_ip("93.184.216.34")
    for ip in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "::ffff:10.0.0.1", "100.64.1.1", "224.0.0.1"):
        assert not is_public_ip(ip), ip


async def test_redirect_to_private_address_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str) -> list[str]:
        return {"public.example": ["93.184.216.34"], "evil.example": ["10.0.0.7"]}.get(host, ["93.184.216.34"])

    monkeypatch.setattr(safe_fetch, "_resolve", fake_resolve)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"location": "http://evil.example/internal"})
        return httpx.Response(200, text="secret")

    with pytest.raises(FetchBlocked):
        await safe_get("http://public.example/job", transport=httpx.MockTransport(handler))

    def to_metadata(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"location": "http://169.254.169.254/latest/meta-data"})

    with pytest.raises(FetchBlocked):
        await safe_get("http://public.example/job", transport=httpx.MockTransport(to_metadata))


async def test_redirect_limit_and_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(safe_fetch, "_resolve", fake_resolve)

    def loop(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://public.example/again"})

    with pytest.raises(FetchBlocked, match="redirects"):
        await safe_get("http://public.example/start", transport=httpx.MockTransport(loop))

    def huge(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (safe_fetch.MAX_BYTES + 10))

    with pytest.raises(FetchBlocked, match="too large"):
        await safe_get("http://public.example/big", transport=httpx.MockTransport(huge))


async def test_robots_txt_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(safe_fetch, "_resolve", fake_resolve)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        assert "JobPilotAI" in request.headers["user-agent"]
        return httpx.Response(200, text="<html>ok</html>", headers={"content-type": "text/html"})

    t = httpx.MockTransport(handler)
    ok = await safe_get("http://public.example/jobs/1", check_robots=True, transport=t)
    assert ok.status == 200
    with pytest.raises(FetchBlocked, match="robots"):
        await safe_get("http://public.example/private/1", check_robots=True, transport=t)


async def test_url_import_endpoint_blocks_internal(make_api) -> None:  # type: ignore[no-untyped-def]
    api = await make_api("ssrf@example.com")
    r = await api.post("/api/jobs/import/manual_url", {"url": "http://169.254.169.254/latest/meta-data/"})
    body = r.json()
    assert body["counts"]["created"] == 0 and body["counts"]["failed"] == 1
    assert "not publicly routable" in body["failed"][0]["error"] or "not allowed" in body["failed"][0]["error"]
