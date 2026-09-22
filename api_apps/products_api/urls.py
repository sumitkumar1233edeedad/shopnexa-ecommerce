from django.urls import path
from .views import (
    ProductListAPIView,
    ProductDetailAPIView,
    ProductReviewAPIView,
    CategoryListAPIView,
    CategoryDetailAPIView,
    ColorListAPIView,
    ColorDetailAPIView,
)

urlpatterns = [
   
    path("products/", ProductListAPIView.as_view(), name="api_product_list"),
 
    path("products/<slug:slug>/reviews/", ProductReviewAPIView.as_view(), name="api_product_reviews"),
 
    path("product/<slug:slug>/", ProductDetailAPIView.as_view(), name="api_product_detail"),

    path("categories/", CategoryListAPIView.as_view(), name="api_category_list"),
 
    path("categories/<slug:slug>/", CategoryDetailAPIView.as_view(), name="api_category_detail"),
 
    path("colors/", ColorListAPIView.as_view(), name="api_color_list"),
 
    path("colors/<slug:slug>/", ColorDetailAPIView.as_view(), name="api_color_detail"),
]