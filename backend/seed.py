"""Idempotent demo data seeding for Forge.

Runs on startup only if the DB is empty. Creates:
- Staff users (all 8 roles)
- Sample brands, categories, products (sanitaryware / bath fittings)
- Sample customers (with portal credentials)
- Sample quotations with realistic totals
- Sample follow-ups and notifications
"""
from datetime import datetime, timedelta, timezone

from auth import hash_password
from db import db
from models import (
    Brand, Category, CustomerInDB, Followup, Notification,
    Product, Quotation, QuotationLineItem, UserInDB,
)

DEMO_STAFF = [
    ("owner@forge.app", "Aarav Kapoor", "owner"),
    ("admin@forge.app", "Ishani Rao", "admin"),
    ("manager@forge.app", "Rohit Verma", "manager"),
    ("sales@forge.app", "Priya Nair", "sales"),
    ("purchase@forge.app", "Kabir Shah", "purchase"),
    ("warehouse@forge.app", "Meera Iyer", "warehouse"),
    ("accounts@forge.app", "Anaya Menon", "accounts"),
    ("worker@forge.app", "Devansh Patel", "worker"),
]

DEMO_PASSWORD = "Forge@2026"

BRANDS = [
    ("Hansgrohe", "Germany"),
    ("Axor",      "Germany"),
    ("Grohe",     "Germany"),
    ("Vitra",     "Turkey"),
    ("Geberit",   "Switzerland"),
]

CATEGORIES = [
    ("Faucets", "faucets"),
    ("Basins", "basins"),
    ("Water Closets", "water-closets"),
    ("Showers", "showers"),
    ("Bathtubs", "bathtubs"),
    ("Accessories", "accessories"),
    ("Flush Plates", "flush-plates"),
]

# Curated sanitaryware imagery (Unsplash / Pexels). All royalty-free.
# Only the 5 supplier brands we distribute: Hansgrohe, Axor, Grohe, Vitra, Geberit.
PRODUCT_SEEDS = [
    # ---- Hansgrohe ----
    ("Talis E Single Lever Basin Mixer", "Faucets", "Hansgrohe", "Chrome", 24800, 18500,
     "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?auto=format&fit=crop&w=800&q=80"),
    ("Metris Single Lever Kitchen Mixer", "Faucets", "Hansgrohe", "Chrome", 32500, 24800,
     "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=800&q=80"),
    ("Croma Select S Overhead 280", "Showers", "Hansgrohe", "Chrome", 28500, 21500,
     "https://images.unsplash.com/photo-1584622781564-1d987f7333c1?auto=format&fit=crop&w=800&q=80"),
    ("Raindance Select E Hand Shower", "Showers", "Hansgrohe", "Chrome", 18500, 13800,
     "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?auto=format&fit=crop&w=800&q=80"),
    # ---- Axor ----
    ("Axor Citterio Basin Mixer 180", "Faucets", "Axor", "Brushed Brass", 68500, 52000,
     "https://images.pexels.com/photos/36718391/pexels-photo-36718391.jpeg?auto=compress&cs=tinysrgb&w=800"),
    ("Axor Uno Single Lever Basin Mixer", "Faucets", "Axor", "Polished Chrome", 58000, 44500,
     "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=800&q=80"),
    ("Axor Starck Organic Overhead", "Showers", "Axor", "Chrome", 82000, 62500,
     "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?auto=format&fit=crop&w=800&q=80"),
    ("Axor Massaud Wash Basin", "Basins", "Axor", "White", 145000, 112000,
     "https://images.unsplash.com/photo-1631679706909-1844bbd07221?auto=format&fit=crop&w=800&q=80"),
    # ---- Grohe ----
    ("Grohe Essence Kitchen Mixer", "Faucets", "Grohe", "Chrome", 28900, 21500,
     "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=800&q=80"),
    ("Grohe Grandera Basin Mixer", "Faucets", "Grohe", "Warm Sunset", 42500, 32800,
     "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=800&q=80"),
    ("Grohe Rainshower SmartActive 310", "Showers", "Grohe", "Chrome", 32500, 24800,
     "https://images.unsplash.com/photo-1584622781564-1d987f7333c1?auto=format&fit=crop&w=800&q=80"),
    ("Grohe Eurosmart CE Concealed", "Faucets", "Grohe", "Chrome", 16500, 12500,
     "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?auto=format&fit=crop&w=800&q=80"),
    # ---- Vitra ----
    ("Vitra S20 Wall-Hung WC", "Water Closets", "Vitra", "White", 32000, 24500,
     "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?auto=format&fit=crop&w=800&q=80"),
    ("Vitra Sento Rimless WC", "Water Closets", "Vitra", "White", 48500, 37500,
     "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=800&q=80"),
    ("Vitra Nest Countertop Basin", "Basins", "Vitra", "White", 22800, 17500,
     "https://images.unsplash.com/photo-1631679706909-1844bbd07221?auto=format&fit=crop&w=800&q=80"),
    ("Vitra Options Vanity Basin", "Basins", "Vitra", "White", 18500, 14200,
     "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?auto=format&fit=crop&w=800&q=80"),
    # ---- Geberit ----
    ("Geberit AquaClean Mera Comfort Shower Toilet", "Water Closets", "Geberit", "White", 385000, 298000,
     "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=800&q=80"),
    ("Geberit Sigma70 Flush Plate", "Flush Plates", "Geberit", "Brushed Steel", 42500, 32500,
     "https://images.unsplash.com/photo-1552321554-5fefe8c9ef14?auto=format&fit=crop&w=800&q=80"),
    ("Geberit Duofix In-Wall Cistern", "Accessories", "Geberit", "Grey", 28500, 21800,
     "https://images.unsplash.com/photo-1584622650111-993a426fbf0a?auto=format&fit=crop&w=800&q=80"),
    ("Geberit Monolith Plus WC Module", "Water Closets", "Geberit", "Umber Glass", 158000, 122000,
     "https://images.unsplash.com/photo-1631679706909-1844bbd07221?auto=format&fit=crop&w=800&q=80"),
]

# Curated sanitaryware imagery (Unsplash / Pexels). All royalty-free.
PRODUCT_SEEDS_LEGACY_REMOVED = True  # replaced by the 5-brand PRODUCT_SEEDS above

DEMO_CUSTOMERS = [
    ("Rajesh Malhotra", "Malhotra Interiors", "customer@forge.app", "+91 98200 12345", "vip", "Mumbai"),
    ("Ananya Reddy", "Studio Reddy", "ananya@studioreddy.in", "+91 98450 22222", "trade", "Bengaluru"),
    ("Vikram Shah", "Shah Residence", "vikram@shahfamily.in", "+91 99870 33333", "retail", "Ahmedabad"),
    ("Kavya Menon", "Menon Architects", "kavya@menonarch.com", "+91 98470 44444", "trade", "Kochi"),
]


async def _empty(collection: str) -> bool:
    return (await db[collection].count_documents({})) == 0


async def resync_catalog_if_needed():
    """Idempotently reconcile brands+categories+products to the current seed constants.
    Runs every startup. Only takes action when the current set differs from the target.
    Safe to run repeatedly. Quotations are unaffected (they store denormalized snapshots
    of name/sku/image/price on each line, so historical quotes keep rendering)."""
    desired = {name for name, _ in BRANDS}
    existing_docs = await db.brands.find({}, {"_id": 0, "name": 1}).to_list(200)
    existing = {d["name"] for d in existing_docs}
    if existing == desired:
        # nothing to do
        return

    # Full reset of catalog data — brands / products / product_usage / categories.
    await db.brands.delete_many({})
    await db.products.delete_many({})
    await db.product_usage.delete_many({})
    await db.categories.delete_many({})

    brand_by_name: dict[str, Brand] = {}
    for name, country in BRANDS:
        b = Brand(name=name, slug=name.lower().replace(" ", "-"), country=country)
        brand_by_name[name] = b
        await db.brands.insert_one(b.dict())

    cat_by_name: dict[str, Category] = {}
    for name, slug in CATEGORIES:
        c = Category(name=name, slug=slug)
        cat_by_name[name] = c
        await db.categories.insert_one(c.dict())

    for i, (name, cat, brand, finish, mrp, price, image) in enumerate(PRODUCT_SEEDS, start=1):
        p = Product(
            name=name,
            sku=f"{brand[:3].upper()}-{cat_by_name[cat].slug[:3].upper()}-{i:03d}",
            brand_id=brand_by_name[brand].id,
            category_id=cat_by_name[cat].id,
            description=f"{name} · {finish} finish · by {brand}. Ships in 5–7 business days.",
            finish=finish,
            material="Solid Brass" if cat == "Faucets" else "Ceramic",
            dimensions="—",
            warranty="10 years" if brand in ("Axor", "Geberit") else "5 years",
            mrp=float(mrp),
            price=float(price),
            stock=25 + (i % 40),
            images=[image],
            tags=[cat.lower(), brand.lower(), finish.lower()],
        )
        await db.products.insert_one(p.dict())


async def seed_if_empty():
    if not await _empty("users"):
        return

    now = datetime.now(timezone.utc)

    # ---- Users ----
    users: dict[str, UserInDB] = {}
    for email, name, role in DEMO_STAFF:
        u = UserInDB(
            email=email, full_name=name, role=role,  # type: ignore[arg-type]
            password_hash=hash_password(DEMO_PASSWORD),
        )
        users[role] = u
        await db.users.insert_one(u.dict())

    # ---- Brands & Categories ----
    brand_by_name: dict[str, Brand] = {}
    for name, country in BRANDS:
        b = Brand(name=name, slug=name.lower().replace(" ", "-"), country=country)
        brand_by_name[name] = b
        await db.brands.insert_one(b.dict())

    cat_by_name: dict[str, Category] = {}
    for name, slug in CATEGORIES:
        c = Category(name=name, slug=slug)
        cat_by_name[name] = c
        await db.categories.insert_one(c.dict())

    # ---- Products ----
    products: list[Product] = []
    for i, (name, cat, brand, finish, mrp, price, image) in enumerate(PRODUCT_SEEDS, start=1):
        p = Product(
            name=name,
            sku=f"{brand[:3].upper()}-{cat_by_name[cat].slug[:3].upper()}-{i:03d}",
            brand_id=brand_by_name[brand].id,
            category_id=cat_by_name[cat].id,
            description=f"Premium {name} in {finish} finish by {brand}. Ships in 5–7 business days.",
            finish=finish,
            material="Solid Brass" if cat == "Faucets" else "Ceramic",
            dimensions="—",
            warranty="10 years" if brand in ("Kohler", "TOTO", "Duravit") else "5 years",
            mrp=float(mrp),
            price=float(price),
            stock=25 + (i % 40),
            images=[image],
            tags=[cat.lower(), brand.lower(), finish.lower()],
        )
        products.append(p)
        await db.products.insert_one(p.dict())

    # ---- Customers ----
    customer_ids: list[str] = []
    for name, company, email, phone, tier, city in DEMO_CUSTOMERS:
        c = CustomerInDB(
            name=name, company=company, email=email.lower(), phone=phone,
            tier=tier, city=city,  # type: ignore[arg-type]
            password_hash=hash_password(DEMO_PASSWORD),
        )
        await db.customers.insert_one(c.dict())
        customer_ids.append(c.id)

    # ---- Quotations ----
    sales_user = users["sales"]
    statuses = ["draft", "sent", "won", "pending_approval", "sent", "won"]
    for idx, cust_id in enumerate(customer_ids * 2):
        cust = await db.customers.find_one({"id": cust_id}, {"_id": 0})
        picked = products[(idx * 3) % len(products): (idx * 3) % len(products) + 4]
        items = [
            QuotationLineItem(
                product_id=p.id, sku=p.sku, name=p.name, image=p.images[0] if p.images else None,
                room=["Master Bath", "Powder Room", "Guest Bath", "Kitchen"][k % 4],
                qty=1 + (k % 3), unit_price=p.price,
                discount_pct=[0, 5, 10, 12][k % 4], tax_pct=18,
            )
            for k, p in enumerate(picked)
        ]
        subtotal = sum(i.qty * i.unit_price for i in items)
        disc = sum(i.qty * i.unit_price * i.discount_pct / 100 for i in items)
        tax = sum(i.tax for i in items)
        q = Quotation(
            number=f"FQ-2026-{idx + 1:04d}",
            customer_id=cust_id,
            customer_name=cust.get("company") or cust["name"],
            status=statuses[idx % len(statuses)],  # type: ignore[arg-type]
            items=items,
            rooms=list({i.room for i in items if i.room}),
            subtotal=round(subtotal, 2),
            discount_total=round(disc, 2),
            tax_total=round(tax, 2),
            grand_total=round(subtotal - disc + tax, 2),
            notes="Prices are valid for 30 days. Delivery in 2–3 weeks after confirmation.",
            valid_until=(now + timedelta(days=30)).isoformat(),
            created_by=sales_user.id,
            created_by_name=sales_user.full_name,
        )
        # nudge timestamps so dashboard sees "this month"
        q_dict = q.dict()
        q_dict["created_at"] = (now - timedelta(days=idx)).isoformat()
        q_dict["updated_at"] = (now - timedelta(days=idx)).isoformat()
        await db.quotations.insert_one(q_dict)

    # ---- Follow-ups ----
    for i, cust_id in enumerate(customer_ids):
        cust = await db.customers.find_one({"id": cust_id}, {"_id": 0})
        f = Followup(
            customer_id=cust_id,
            customer_name=cust.get("company") or cust["name"],
            due_at=(now + timedelta(hours=i * 6)).isoformat(),
            channel=["call", "whatsapp", "email", "visit"][i % 4],  # type: ignore[arg-type]
            note=["Confirm order", "Share latest catalog", "Payment reminder", "Site visit"][i % 4],
            assigned_to=sales_user.id,
        )
        await db.followups.insert_one(f.dict())

    # ---- Notifications for the sales user ----
    for i in range(5):
        n = Notification(
            user_id=sales_user.id,
            kind=["info", "success", "warning", "info", "success"][i],  # type: ignore[arg-type]
            title=["New quotation approved", "Payment received", "Follow-up due", "Stock low", "Customer replied"][i],
            body="—",
        )
        await db.notifications.insert_one(n.dict())
