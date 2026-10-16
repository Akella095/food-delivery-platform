"""initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

order_status_enum = postgresql.ENUM(
    "pending", "confirmed", "preparing", "on_the_way", "delivered", "cancelled", name="order_status"
)


def upgrade() -> None:
    bind = op.get_bind()
    order_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "restaurants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_restaurants_owner_id", "restaurants", ["owner_id"])
    op.create_index("ix_restaurants_is_active", "restaurants", ["is_active"])

    op.create_table(
        "menu_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("restaurant_id", sa.String(length=36), sa.ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_menu_items_restaurant_id", "menu_items", ["restaurant_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("courier_id", sa.String(length=36), nullable=True),
        sa.Column("restaurant_id", sa.String(length=36), sa.ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "confirmed", "preparing", "on_the_way", "delivered", "cancelled",
                name="order_status", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_courier_id", "orders", ["courier_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("menu_item_id", sa.String(length=36), sa.ForeignKey("menu_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "courier_status",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("courier_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("vehicle_type", sa.String(length=50), nullable=False, server_default="bike"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_courier_status_courier_id", "courier_status", ["courier_id"])


def downgrade() -> None:
    op.drop_table("courier_status")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("menu_items")
    op.drop_table("restaurants")
    order_status_enum.drop(op.get_bind(), checkfirst=True)
