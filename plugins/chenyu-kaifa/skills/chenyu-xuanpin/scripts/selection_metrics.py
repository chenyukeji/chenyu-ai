"""Extract only visible SellerSprite values tied to a verified product row."""
import re

def parse_bsr(value):
    lines=[re.sub(r"\s+", " ", line).strip() for line in str(value or "").splitlines() if line.strip()]
    if not lines or not re.fullmatch(r"[\d,]+",lines[0]): return {}
    result={"rank":int(lines[0].replace(",", ""))}
    pattern=r"[↑↓+\-−]?\s*\d[\d,]*(?:\.\d+)?"
    if len(lines)>1 and re.fullmatch(pattern,lines[1]): result["rank_change"]=lines[1]
    if len(lines)>2 and re.fullmatch(pattern+r"\s*%",lines[2]): result["rank_percent"]=lines[2]
    return result

def parse_package(items):
    if not isinstance(items,list): return {}
    candidates={}
    for item in items:
        if not isinstance(item,str):continue
        match=re.match(r"^\s*(包装重量|包裹重量|包装尺寸|包裹尺寸)\s*[:：]\s*(.+?)\s*$",item)
        if not match:continue
        label,value=match.groups(); value=re.sub(r"\s+"," ",value).strip()
        if len(value)>160 or not re.search(r"\d",value):continue
        key="package_weight" if "重量" in label else "package_dimensions"
        candidates.setdefault(key,set()).add(value)
    return {key:next(iter(values)) for key,values in candidates.items() if len(values)==1}

def extract(record):
    cells=record.get("raw_cells") if isinstance(record.get("raw_cells"),dict) else {}
    bsr=next((value for key,value in cells.items() if re.sub(r"\s+","",str(key)).casefold() in {"大类bsr","bsr"}),None)
    parsed=parse_bsr(bsr)
    try: known=int(str(record.get("bsr")).replace(",", ""))
    except (TypeError,ValueError):known=None
    result=parse_package(record.get("product_info"))
    if known and parsed.get("rank")==known:
        result.update({key:parsed[key] for key in ("rank_change","rank_percent") if key in parsed})
        if "rank_change" in result or "rank_percent" in result: result["rank_basis"]=known
    return result
