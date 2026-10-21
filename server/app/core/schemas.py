from pydantic import BaseModel, ConfigDict


class StrictInput(BaseModel):
    """Base for request bodies: unexpected fields are rejected (422), not
    silently dropped, closing the mass-assignment class of bug even though
    nothing in this codebase does blind **body.dict() assignment to ORM
    models today."""

    model_config = ConfigDict(extra="forbid")
