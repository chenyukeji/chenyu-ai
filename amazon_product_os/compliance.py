from __future__ import annotations

from typing import Any


def assess_compliance(profile: dict[str, Any], marketplace: str = "EU") -> dict[str, Any]:
    """Provide a screening gate, not legal certification."""
    flag_names = {"textile", "toy", "children", "electronic", "battery", "food_contact", "ppe", "packaging"}
    flags = {key: bool(profile.get(key)) for key in flag_names}
    requirements = [
        {"code": "GPSR", "reason": "EU general product safety and traceability", "required": marketplace.upper() in {"EU", "DE", "FR", "IT", "ES"}},
        {"code": "REACH", "reason": "Chemical/substance restrictions", "required": marketplace.upper() in {"EU", "DE", "FR", "IT", "ES"}},
    ]
    if flags.get("textile"):
        requirements.append({"code": "TEXTILE_LABEL", "reason": "Fibre composition and local-language labelling", "required": True})
    if flags.get("toy"):
        requirements.extend(
            [
                {"code": "CE", "reason": "Toy Safety Directive conformity", "required": True},
                {"code": "EN71", "reason": "Toy safety testing", "required": True},
            ]
        )
    if flags.get("electronic"):
        requirements.extend(
            [
                {"code": "CE", "reason": "Applicable electrical/EMC/RoHS conformity", "required": True},
                {"code": "WEEE", "reason": "Electrical equipment producer responsibility", "required": True},
                {"code": "ROHS", "reason": "Restricted substances in electronics", "required": True},
            ]
        )
    if flags.get("battery"):
        requirements.append({"code": "BATTERY_EPR", "reason": "Battery producer responsibility and marking", "required": True})
    if flags.get("food_contact"):
        requirements.append({"code": "FOOD_CONTACT", "reason": "Food-contact material declarations/testing", "required": True})
    if flags.get("ppe"):
        requirements.extend(
            [
                {"code": "CE", "reason": "PPE Regulation conformity", "required": True},
                {"code": "PPE_TECHNICAL_FILE", "reason": "PPE testing and technical documentation", "required": True},
            ]
        )
    if flags.get("packaging", True):
        requirements.append({"code": "PACKAGING_EPR", "reason": "Marketplace-country packaging EPR", "required": True})

    supplied = {str(code).upper() for code in profile.get("documents", [])}
    missing = sorted({item["code"] for item in requirements if item["required"] and item["code"] not in supplied})
    high_risk_flags = [flag for flag in ("toy", "electronic", "battery", "food_contact", "ppe") if flags.get(flag)]
    if high_risk_flags and missing:
        risk = "high"
    elif missing:
        risk = "medium"
    else:
        risk = "low"
    return {
        "risk": risk,
        "profile_flags": sorted(key for key, enabled in flags.items() if enabled),
        "requirements": requirements,
        "missing_evidence": missing,
        "hard_gate": risk == "high",
        "disclaimer": "Screening only. Confirm current marketplace and legal requirements with qualified compliance specialists before launch.",
    }
