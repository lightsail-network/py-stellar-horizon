"""The base class of every model, and the link that resources carry."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

__all__ = ["Link", "Model"]


class Model(BaseModel):
    """The base class of every Horizon resource.

    Models are frozen: assigning to a field raises. They compare by value. Fields that
    this package does not know yet are kept, and can be read from `model_extra`.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True, extra="allow", populate_by_name=True
    )


class Link(Model):
    """A link to a related resource, as Horizon writes it in `_links`."""

    href: str
    templated: bool = False
