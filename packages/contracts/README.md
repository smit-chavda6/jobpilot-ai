# JobPilot AI — Contracts & Schemas

This package defines shared schemas and data contracts for JobPilot AI across the backend API, workers, and frontend web client.

## Core Schemas
1. **User & Auth**: Registration, Login, Session, Profile, Fact
2. **Jobs**: RawJob, JobDraft, JobListing, SourceMetadata, ComplianceStatus
3. **Matching**: HardFilterResult, MatchScore, FitReason, MissingRequirement, MatchExplanation
4. **Application**: ApplicationState, ApplicationActivity, ApprovalRecord, GroundedTailoring
5. **Errors**: RFC 7807-compatible structured ErrorEnvelope
