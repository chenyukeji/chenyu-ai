from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class Candidate:
    product_type: str
    source: str
    evidence: dict[str, Any]
    marketplace: str = ""
    source_ref: str = ""
    observed_at: str = field(default_factory=lambda: date.today().isoformat())
    score: float | None = None
    representative_asins: list[str] = field(default_factory=list)
    representative_titles: list[str] = field(default_factory=list)
    price_band: dict[str, float] = field(default_factory=dict)
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        self.product_type = self.product_type.strip()
        self.source = self.source.strip()
        if not self.product_type:
            raise ValueError("Candidate.product_type cannot be empty")
        if self.source not in {"New Releases", "Historical Spike", "Manual"}:
            raise ValueError(f"Unsupported candidate source: {self.source}")
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("Candidate.score must be between 0 and 100")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Candidate":
        return cls(**{key: val for key, val in value.items() if key in cls.__dataclass_fields__})


@dataclass(slots=True)
class ProductMaster:
    product_name: str
    sku: str
    quantity: str
    color: str
    material: str
    dimensions: dict[str, Any]
    weight_g: float
    packaging: str
    target_audience: str
    core_functions: list[str]
    compliance: dict[str, Any]
    brand: str = ""
    ean: str = ""
    manufacturer: str = ""
    responsible_person: str = ""
    country_of_origin: str = "China"
    target_price: float | None = None
    currency: str = "EUR"
    initial_inventory: int = 0
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        required = {
            "product_name": self.product_name,
            "sku": self.sku,
            "quantity": self.quantity,
            "color": self.color,
            "material": self.material,
            "packaging": self.packaging,
            "target_audience": self.target_audience,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"Missing Product Master fields: {', '.join(missing)}")
        if self.weight_g <= 0:
            raise ValueError("ProductMaster.weight_g must be positive")
        if not self.core_functions:
            raise ValueError("ProductMaster.core_functions cannot be empty")
        if self.initial_inventory < 0:
            raise ValueError("ProductMaster.initial_inventory cannot be negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProductMaster":
        return cls(**{key: val for key, val in value.items() if key in cls.__dataclass_fields__})
