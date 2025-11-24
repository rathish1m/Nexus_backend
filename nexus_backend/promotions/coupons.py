import random
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Set

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from main.models import Coupon


def _random_code(*, length: int = 10, prefix: str = "") -> str:
    # Unambiguous uppercase alnum (no 0/O, 1/I)
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    body = "".join(random.choice(alphabet) for _ in range(max(1, length)))
    return f"{prefix}{body}" if prefix else body


@transaction.atomic
def generate_unique_coupon(
    *, CouponModel, length: int = 10, prefix: str = "", **coupon_kwargs
):
    """
    Create & return a unique Coupon row.
    REQUIRED:
      - CouponModel: your Coupon model class (pass as keyword!)
    OPTIONAL:
      - length: code body length (prefix not counted)
      - prefix: static prefix placed before the random body
      - **coupon_kwargs: any extra fields you want on the created row
    """
    for _ in range(20):
        code = _random_code(length=length, prefix=prefix)
        if not CouponModel.objects.filter(code=code).exists():
            return CouponModel.objects.create(code=code, **coupon_kwargs)
    raise RuntimeError(
        "Could not generate a unique coupon code after several attempts."
    )


def _coerce_decimal_or_none(value) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid decimal value")
    return d


@transaction.atomic
def bulk_generate_coupons(
    *,
    CouponModel,
    count: int = 50,
    length: int = 10,
    prefix: str = "",
    discount_type: str = "percent",  # "percent" | "fixed"
    percent_off: Optional[Decimal] = None,
    amount_off: Optional[Decimal] = None,
    valid_from=None,  # datetime | ISO str | None
    valid_to=None,  # datetime | ISO str | None
    per_user_limit: int = 1,
    max_redemptions: int = 1,
    is_active: bool = True,  # ← Add this line
    notes: str = "",
    created_by=None,
    tags: Optional[
        Iterable[str]
    ] = None,  # if your model has tags (JSONField/ManyToMany)
) -> Dict[str, Any]:
    """
    Create many coupons quickly and safely.

    Returns:
      {
        "count": <created_count>,
        "sample_codes": ["ABC...", "..."],
        "prefix": "<PREFIX>",
        "length": <length>,
        "discount_type": "percent|fixed",
        "percent_off": <Decimal or None>,
        "amount_off": <Decimal or None>,
      }

    Assumptions:
      - Coupon.code is unique (DB unique constraint or at least indexed)
      - Coupon fields (adapt names as needed):
        code (str, unique), discount_type (str), percent_off (Decimal|None),
        amount_off (Decimal|None), valid_from (datetime|None), valid_to (datetime|None),
        per_user_limit (int), max_redemptions (int), is_active (bool),
        notes (str), created_by (FK to User, nullable), tags (optional)
    """

    # ---------- Validate inputs ----------
    count = int(count or 0)
    if count <= 0:
        raise ValueError("count must be > 0")

    length = max(4, int(length or 10))
    prefix = (prefix or "").strip().upper()

    discount_type = (discount_type or "percent").strip().lower()
    if discount_type not in {"percent", "fixed"}:
        raise ValueError("discount_type must be 'percent' or 'fixed'")

    # coerce discounts
    if discount_type == "percent":
        percent_off = _coerce_decimal_or_none(percent_off)
        if percent_off is None or percent_off <= 0 or percent_off > 100:
            raise ValueError("percent_off must be in (0, 100]")
        amount_off = None
    else:
        amount_off = _coerce_decimal_or_none(amount_off)
        if amount_off is None or amount_off <= 0:
            raise ValueError("amount_off must be > 0")
        percent_off = None

    per_user_limit = max(0, int(per_user_limit or 1))
    max_redemptions = max(0, int(max_redemptions or 1))
    notes = (notes or "").strip()

    # parse/normalize datetimes if ISO strings passed
    def _normalize_dt(dt):
        if not dt:
            return None
        if isinstance(dt, str):
            parsed = parse_datetime(dt)
            if parsed is None:
                raise ValueError(f"Invalid datetime string: {dt}")
            return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
        return dt

    valid_from = _normalize_dt(valid_from)
    valid_to = _normalize_dt(valid_to)
    if valid_from and valid_to and valid_to <= valid_from:
        raise ValueError("valid_to must be greater than valid_from")

    # ---------- Generate codes in memory and ensure uniqueness ----------
    # Strategy:
    # 1) generate a superset (with headroom)
    # 2) remove codes already in DB
    # 3) if not enough unique remain, loop until we have 'count'
    desired = count
    codes: Set[str] = set()
    headroom_factor = 1.25  # generate a bit more to reduce DB lookups
    max_rounds = 10

    def _gen_batch(n: int) -> List[str]:
        return [generate_unique_coupon(length=length, prefix=prefix) for _ in range(n)]

    rounds = 0
    while len(codes) < desired and rounds < max_rounds:
        rounds += 1
        to_gen = max(1, int((desired - len(codes)) * headroom_factor))
        candidate = _gen_batch(to_gen)

        # Remove anything that already exists in DB
        existing = set(
            Coupon.objects.filter(code__in=candidate).values_list("code", flat=True)
        )
        for c in candidate:
            if c not in existing:
                codes.add(c)

    if len(codes) < desired:
        # As a last attempt, try generating one-by-one with DB check
        while len(codes) < desired:
            c = generate_unique_coupon(length=length, prefix=prefix)
            if not Coupon.objects.filter(code=c).exists():
                codes.add(c)

    # ---------- Build and bulk_create ----------
    now = timezone.now()
    objs = []
    for code in list(codes)[:desired]:
        obj = Coupon(
            code=code,
            discount_type=discount_type,
            percent_off=percent_off,
            amount_off=amount_off,
            valid_from=valid_from,
            valid_to=valid_to,
            per_user_limit=per_user_limit,
            max_redemptions=max_redemptions,
            is_active=True,
            notes=notes,
            created_by=created_by,
            created_at=getattr(Coupon, "created_at", now)
            and now,  # if you have auto_add, it's ignored
        )
        objs.append(obj)

    created = Coupon.objects.bulk_create(objs, ignore_conflicts=True)
    created_count = len(created)

    # Optional: if you support tags (ManyToMany or JSONField), attach them here
    if created_count and tags:
        try:
            # Example if you have a many-to-many "tags" via a Tag model:
            # from .models import Tag
            # tag_objs = list(Tag.objects.filter(name__in=list(tags)))
            # for c in created:
            #     c.tags.add(*tag_objs)
            pass
        except Exception:
            # Silently ignore tag errors to keep coupon creation resilient
            pass

    # ---------- Result ----------
    sample_codes = [c.code for c in created[: min(10, created_count)]]
    return {
        "count": created_count,
        "sample_codes": sample_codes,
        "prefix": prefix,
        "length": length,
        "discount_type": discount_type,
        "percent_off": str(percent_off) if percent_off is not None else None,
        "amount_off": str(amount_off) if amount_off is not None else None,
    }
