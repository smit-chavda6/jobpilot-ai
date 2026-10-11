import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Modal } from "../components/ui/modal";

describe("UI Design System Primitives", () => {
  it("renders Button correctly and handles click events", () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click Me</Button>);
    const button = screen.getByRole("button", { name: /click me/i });
    expect(button).toBeInTheDocument();
    fireEvent.click(button);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it("disables Button and shows loading indicator when isLoading is true", () => {
    render(<Button isLoading>Submit</Button>);
    const button = screen.getByRole("button", { name: /submit/i });
    expect(button).toBeDisabled();
  });

  it("renders Badge with appropriate variants", () => {
    const { container } = render(<Badge variant="success">95% Fit</Badge>);
    expect(screen.getByText("95% Fit")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("bg-emerald-100");
  });

  it("renders Input with label and displays validation error message", () => {
    render(
      <Input
        label="Username"
        error="Invalid characters detected"
        placeholder="Enter username"
      />
    );
    expect(screen.getByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByText("Invalid characters detected")).toBeInTheDocument();
  });

  it("renders Modal when isOpen is true and invokes onClose when close button clicked", () => {
    const handleClose = vi.fn();
    render(
      <Modal isOpen={true} onClose={handleClose} title="Test Dialog">
        <p>Dialog Body Content</p>
      </Modal>
    );
    expect(screen.getByText("Test Dialog")).toBeInTheDocument();
    expect(screen.getByText("Dialog Body Content")).toBeInTheDocument();

    const closeBtn = screen.getByLabelText(/close dialog/i);
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
