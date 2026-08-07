# pylint: disable=missing-module-docstring,missing-class-docstring
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class CamelCaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )
