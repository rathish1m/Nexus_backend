from datetime import timedelta

import factory

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    CompanyKYC,
    Coupon,
    DiscountType,
    InstallationActivity,
    Order,
    PersonalKYC,
    Promotion,
    StarlinkKit,
    StarlinkKitInventory,
    Subscription,
    SubscriptionPlan,
)

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    full_name = factory.Faker("name")
    phone = factory.Sequence(lambda n: f"+243{n:010d}")
    is_active = True
    roles = ["customer"]  # Add customer role for client_app views


class StaffUserFactory(UserFactory):
    is_staff = True


class PersonalKYCFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PersonalKYC

    user = factory.SubFactory(UserFactory)
    full_name = factory.Faker("name")
    address = factory.Faker("address")
    document_number = factory.Sequence(lambda n: f"ID{n:06d}")


class CompanyKYCFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CompanyKYC

    user = factory.SubFactory(UserFactory)
    company_name = factory.Faker("company")
    address = factory.Faker("address")
    rccm = factory.Sequence(lambda n: f"RCCM{n:06d}")
    nif = factory.Sequence(lambda n: f"NIF{n:06d}")
    id_nat = factory.Sequence(lambda n: f"IDNAT{n:06d}")
    representative_name = factory.Faker("name")


class SubscriptionPlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SubscriptionPlan

    name = factory.Sequence(lambda n: f"Plan {n}")
    category_name = "Standard Category"
    plan_type = "limited_standard"
    site_type = "flexible"
    standard_data_gb = factory.Faker("random_int", min=10, max=1000)
    monthly_price_usd = factory.Faker(
        "pydecimal", left_digits=3, right_digits=2, positive=True
    )
    is_active = True


class StarlinkKitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StarlinkKit

    name = factory.Sequence(lambda n: f"Kit {n}")
    model = factory.Sequence(lambda n: f"Model{n}")
    kit_type = "standard"  # Default to standard kit
    base_price_usd = factory.Faker(
        "pydecimal", left_digits=4, right_digits=2, positive=True
    )


class StarlinkKitInventoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StarlinkKitInventory

    kit = factory.SubFactory(StarlinkKitFactory)
    serial_number = factory.Sequence(lambda n: f"SN{n:08d}")
    is_assigned = False


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    plan = factory.SubFactory(SubscriptionPlanFactory)
    total_price = factory.Faker(
        "pydecimal", left_digits=4, right_digits=2, positive=True
    )
    latitude = factory.Faker("latitude")
    longitude = factory.Faker("longitude")
    status = "pending_payment"
    payment_status = "unpaid"


class SubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Subscription

    user = factory.SubFactory(UserFactory)
    plan = factory.SubFactory(SubscriptionPlanFactory)
    status = "active"
    billing_cycle = "monthly"


class InstallationActivityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = InstallationActivity

    order = factory.SubFactory(OrderFactory)
    status = "completed"
    completed_at = factory.LazyFunction(lambda: timezone.now())


class PromotionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Promotion

    name = factory.Sequence(lambda n: f"Promotion {n}")
    active = True
    discount_type = DiscountType.PERCENT
    value = factory.Faker(
        "pydecimal", left_digits=2, right_digits=2, positive=True, max_value=50
    )
    starts_at = factory.LazyFunction(lambda: timezone.now() - timedelta(days=1))
    ends_at = factory.LazyFunction(lambda: timezone.now() + timedelta(days=30))


class CouponFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Coupon

    code = factory.Sequence(lambda n: f"COUPON{n}")
    is_active = True
    discount_type = DiscountType.PERCENT
    percent_off = factory.Faker(
        "pydecimal", left_digits=2, right_digits=2, positive=True, max_value=50
    )
    valid_from = factory.LazyFunction(lambda: timezone.now() - timedelta(days=1))
    valid_to = factory.LazyFunction(lambda: timezone.now() + timedelta(days=30))
