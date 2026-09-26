import os
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings
from django.http import FileResponse, HttpResponseNotFound
from apps.accounts.views import *
from apps.products.views import *
from apps.cart.views import *
from apps.order.views import *
from apps.payment.views import *


def favicon_view(request):
    favicon_path = settings.BASE_DIR / 'static' / 'images' / 'favicon.ico'
    if os.path.exists(favicon_path):
        return FileResponse(open(favicon_path, 'rb'), content_type='image/x-icon')
    return HttpResponseNotFound()


urlpatterns = [
    path('favicon.ico', favicon_view, name='favicon'),

    path('', home, name = 'home'),
    path('admin/', admin.site.urls),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('verify-otp/', verify_otp_view, name='verify_otp'),
    path('resend-otp/', resend_otp_view, name='resend_otp'),
    path('forgot-password/', forgot_password_view, name='forgot_password'),
    path('verify-reset-otp/', verify_reset_otp_view, name='verify_reset_otp'),
    path('reset-password/', reset_password_view, name='reset_password'),
    path('resend-reset-otp/', resend_reset_otp_view, name='resend_reset_otp'),
    path('change-password/', change_password_view, name='change_password'),
    path('logout/', logout_view, name='logout'),
    path('profile/', profile_view, name='profile_default'),
    path('profile/<slug:slug>/', profile_view, name='profile'),
    path('profile/update/', update_profile, name='update_default'),
    path('profile/<slug:slug>/update/', update_profile, name='update'),
    path("wishlist/toggle/<slug:slug>/", toggle_wishlist, name="toggle_wishlist"),
    path("wishlist/", wishlist_view, name="wishlist"),
    path("wishlist/remove/<slug:slug>/", remove_from_wishlist, name="remove_from_wishlist"),
    path("address/add/", add_address, name="add_address"),
    path("address/", address, name="address"),
    path("address/delete/<slug:slug>/", delete_address, name="delete_address"),
    
    
    path('product/<slug:slug>/', product_detail, name='product_detail'),
    path('products/', product_list, name='products'),
    path('products', product_list),
    path('category_page/', category_page, name='category_page'),
    path('product/<slug:slug>/review/', submit_review, name='submit_review'),
    path('cart/', cart , name='cart'),
    path("add/<slug:variant_slug>/", add_to_cart, name="add_to_cart"),
    path("increase/<slug:variant_slug>/", increase_quantity, name="increase_quantity"),
    path("decrease/<slug:variant_slug>/", decrease_quantity, name="decrease_quantity"),
    path("remove/<slug:variant_slug>/", remove_from_cart, name="remove_from_cart"),
    
    path("clear/", clear_cart, name="clear_cart"),
    path("checkout/", checkout_view, name="checkout"),
    path("place-order/", place_order_view, name="place_order"),
    path("confirmation/<slug:order_slug>/", order_confirmation_view, name="order_confirmation"),
    path("my-orders/", my_orders_view, name="my_orders"),
    path("order/<slug:order_slug>/", order_detail_view, name="order_detail"),
    path("process/<slug:order_slug>/", payment_process, name="payment_process"),
    
    path("payment/", include("apps.payment.urls")),
    path("adminpanel/", include("apps.admin_pannel.urls")),
    path("coupons/", include("apps.coupons.urls")),
    path("chat/", include("apps.chat.urls")),

    ## api ##
    path('api/', include('api_apps.accounts_api.urls')),
    path('api/', include('api_apps.products_api.urls')),
    path('api/', include('api_apps.cart_api.urls')),
    path('api/', include('api_apps.orders_api.urls')),
    path('api/', include('api_apps.coupons_api.urls')),
    path('api/', include('api_apps.payment_api.urls')),
    path('api/', include('api_apps.chat_api.urls')),
    path('api/', include('api_apps.admin_api.urls')),

    ## AI Assistant (API & Web) ##
    path('', include('ai.urls')),
]
if settings.DEBUG:
    urlpatterns += [
        path("__debug__/", include("debug_toolbar.urls")),
    ]
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )

