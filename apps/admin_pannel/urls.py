from django.urls import path
from . import views
from .views import *
from apps.chat import views as chat_views

urlpatterns = [

  
    path("login/", views.admin_login, name="admin_login"),
    path("logout/", views.admin_logout, name="admin_logout"),
 
    path("dashboard/", views.dashboard, name="admin_dashboard"),

     
    path("products/", views.product_list, name="admin_products"),
    path("products/add/", views.product_add, name="admin_product_add"),
    path(
        "products/<slug:slug>/",
        views.product_detail,
        name="admin_product_detail"
    ),
    path(
        "products/<slug:slug>/edit/",
        views.product_edit,
        name="admin_product_edit"
    ),
    path(
        "products/<slug:slug>/delete/",
        views.product_delete,
        name="admin_product_delete"
    ),
    path(
        "products/image/<int:image_id>/delete/",
        views.product_image_delete,
        name="admin_product_image_delete"
    ),

     
    path("categories/", views.category_list, name="admin_categories"),
    path(
        "categories/add/",
        views.category_add,
        name="admin_category_add"
    ),
    path(
        "categories/edit/<slug:slug>/",
        category_edit,
        name="admin_category_edit"
    ),

    path(
        "categories/delete/<slug:slug>/",
        category_delete,
        name="admin_category_delete"
    ),

    
    path("variants/", views.variant_list, name="admin_variants"),
    path(
        "variants/add/",
        views.variant_add,
        name="admin_variant_add"
    ),
    path(
        "variants/edit/<slug:slug>/",
        variant_edit,
        name="admin_variant_edit"
    ),

    path(
        "variants/delete/<slug:slug>/",
        variant_delete,
        name="admin_variant_delete"
    ),

    
    path("orders/", views.order_list, name="admin_orders"),
    path(
        "orders/<slug:slug>/",
        views.order_detail,
        name="admin_order_detail"
    ),
    path(
        "orders/<slug:slug>/status/",
        views.update_order_status,
        name="admin_order_status"
    ),

    # Users Management
    path("users/", views.user_list, name="admin_users"),
    path("users/list/", views.user_list, name="admin_user_list"),

    path("customers/", views.customer_list, name="admin_customers"),
    path(
        "customers/<slug:slug>/",
        views.customer_detail,
        name="admin_customer_detail"
    ),
 
    path("reviews/", views.review_list, name="admin_reviews"),
    path(
        "reviews/<slug:slug>/",
        views.review_detail,
        name="admin_review_detail"
    ),
    path(
        "reviews/<slug:slug>/delete/",
        views.review_delete,
        name="admin_review_delete"
    ),

    path("colors/", views.color_list, name="admin_colors"),
    path("colors/add/", views.color_add, name="admin_color_add"),
    path("colors/edit/<slug:slug>/", views.color_edit, name="admin_color_edit"),
    path("colors/delete/<slug:slug>/", views.color_delete, name="admin_color_delete"),

    # Coupons
    path("coupons/", views.coupon_list, name="admin_coupons"),
    path("coupons/add/", views.coupon_add, name="admin_coupon_add"),
    path("coupons/configuration/", views.coupon_configuration, name="admin_coupon_configuration"),
    path("coupons/<slug:slug>/", views.coupon_detail, name="admin_coupon_detail"),
    path("coupons/<slug:slug>/edit/", views.coupon_edit, name="admin_coupon_edit"),
    path("coupons/<slug:slug>/delete/", views.coupon_delete, name="admin_coupon_delete"),
    path("coupons/<slug:slug>/toggle/", views.coupon_toggle, name="admin_coupon_toggle"),
    path("coupons/<slug:slug>/broadcast/", views.coupon_broadcast, name="admin_coupon_broadcast"),

    # Chat Support
    path("chat/", chat_views.admin_chat_list, name="admin_chat_list"),
    path("chat/<slug:slug>/", chat_views.admin_chat_room, name="admin_chat_room"),
    path("chat/<slug:slug>/status/", chat_views.admin_chat_status, name="admin_chat_status"),

    # Staff & Permissions Management
    path("staff/", views.staff_list, name="admin_staff_list"),
    path("staff/add/", views.staff_add, name="admin_staff_add"),
    path("staff/<slug:slug>/permissions/", views.staff_permissions, name="admin_staff_permissions"),
    path("staff/<slug:slug>/remove/", views.staff_remove, name="admin_staff_remove"),
]
