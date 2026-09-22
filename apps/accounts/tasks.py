import logging
from celery import shared_task
from django.core.mail import EmailMultiAlternatives, send_mail
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.coupons.models import Coupon
import random
import re
import logging
from datetime import timedelta
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
 
 

User = get_user_model()
logger = logging.getLogger(__name__)


# ==============================================================================
# REGISTRATION WELCOME EMAIL TASK
# ==============================================================================

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="apps.accounts.tasks.send_registration_email"
)
def send_registration_email(self, user_id):
    """
    Celery background task to send a registration welcome email.
    Takes only user_id to prevent passing unserializable User instances.
    """
    logger.info(f"Task started: Sending registration email for user_id {user_id}.")
    try:
        user = User.objects.filter(id=user_id).first()
        if not user or not user.email:
            logger.warning(f"Task aborted: User with ID {user_id} not found or has no email.")
            return f"User {user_id} not found or no email."

        user_name = user.first_name if user.first_name else user.username
        subject = "🎉 Welcome to AI Store! Registration Successful"
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", settings.EMAIL_HOST_USER)
        site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")

        plain_message = (
            f"Hello {user_name},\n\n"
            f"Thank you for registering at AI Store!\n\n"
            f"Your account has been created successfully. Explore our latest products and start shopping:\n"
            f"{site_url}/\n\n"
            f"If you have any questions, feel free to reply to this email.\n\n"
            f"Warm regards,\n"
            f"AI Store Team"
        )

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=[user.email],
            fail_silently=False,
        )

        logger.info(f"Task completed: Registration email sent successfully to {user.email}.")
        return f"Registration email sent to {user.email}"

    except Exception as exc:
        logger.error(f"Task error: Failed to send registration email to User ID {user_id}: {exc}")
        raise self.retry(exc=exc)



# ==============================================================================
# OTP EMAIL TASKS
# ==============================================================================

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="apps.accounts.tasks.send_otp_email_task"
)
def send_otp_email_task(self, email, user_display, otp_code, purpose="registration"):

    # print('22222222222222222222222')
    """
    Asynchronous Celery task to send OTP emails in the background.
    """
    logger.info(f"Task started: Sending OTP email to {email} for purpose '{purpose}'.")
    try:
        if purpose == "registration":
            subject = "🔐 AI Store - Verify Your Email (OTP)"
            body_text = "Thank you for registering. Please enter the following 6-digit code to verify your account."
        else:
            subject = "🔑 AI Store - Password Reset Request (OTP)"
            body_text = "We received a request to reset your password. Use the following 6-digit code to complete the reset."

        context = {
            "user_display": user_display,
            "otp_code": otp_code,
            "body_text": body_text,
        }

        # Render HTML template
        html_message = render_to_string(
            "accounts/otp_email.html",
            context
        )

        plain_message = (
            f"Hello {user_display},\n\n"
            f"{body_text}\n\n"
            f"Your OTP Code: {otp_code}\n\n"
            f"⏱️ This OTP is strictly valid for 10 minutes.\n"
            f"If you did not request this, please ignore this email.\n\n"
            f"Warm regards,\n"
            f"AI Store Team"
        )

        

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "AI Store <storeai.otp@gmail.com>")
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=from_email,
            to=[email]
        )
        msg.attach_alternative(html_message, "text/html")
        msg.send(fail_silently=False)

        logger.info(f"Task completed: OTP email sent successfully to {email}.")
        return f"OTP sent to {email}"

    except Exception as exc:
        logger.error(f"Task error: Failed to send OTP email to {email}: {exc}")
        raise self.retry(exc=exc)

# acutally right now this is not used in my project 
@shared_task(name="apps.accounts.tasks.cleanup_expired_otps_task")
def cleanup_expired_otps_task():
    """
    Clean up expired temp_otp values from user records (older than 10 minutes).
    """
    now = timezone.now()
    cutoff = now - timedelta(minutes=10)
    updated_count = User.objects.filter(
        otp_created_at__lt=cutoff,
        temp_otp__isnull=False
    ).update(temp_otp=None, otp_created_at=None)
    logger.info(f"Task completed: Cleared {updated_count} expired temp_otp records.")
    return updated_count


# ==============================================================================
# PROMOTIONAL COUPON BROADCAST TASKS
# ==============================================================================

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="apps.accounts.tasks.broadcast_coupon_announcement_task"
)
def broadcast_coupon_announcement_task(self, coupon_id):
    """
    Celery background task to format and broadcast promotional coupon emails
    to all active registered customers.
    """
    
    logger.info(f"Task started: Broadcasting coupon ID {coupon_id}.")
    try:
        # 1. Get the coupon
        coupon = Coupon.objects.filter(id=coupon_id).first()
        if not coupon:
            logger.error(f"Coupon ID {coupon_id} not found for broadcast.")
            return f"Coupon {coupon_id} not found."

        # 2. Get active users with email
        active_users = User.objects.filter(is_active=True, email__isnull=False).exclude(email="")
        if not active_users.exists():
            logger.info("No active users found with valid email addresses.")
            return "No active users to email."

        discount_text = (
            f"{int(coupon.discount_value)}% OFF"
            if coupon.discount_type == "percentage"
            else f"₹{int(coupon.discount_value)} FLAT OFF"
        )
        subject = f"🔥 Exclusive Offer: Get {discount_text} with code {coupon.code}!"
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "AI Store <storeai.otp@gmail.com>")
        site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")

        # 3. Send email & 4. Count successful / 5. Count failed emails
        sent_count = 0
        failed_count = 0

        for user in active_users:
            if not user.email:
                continue
            user_name = user.first_name if user.first_name else user.username
            
            context = {
                "user_name": user_name,
                "coupon": coupon,
                "discount_text": discount_text,
                "minimum_order_amount": int(
                    coupon.minimum_order_amount
                ),
                "valid_until": coupon.valid_until.strftime(
                    "%d %b %Y"
                ),
                "site_url": site_url,
            }

            html_message = render_to_string(
                "adminpanel/coupon_broadcast.html",
                context
            )

            plain_message = (
                f"Hello {user_name},\n\n"
                f"We are excited to share a special promotion with you!\n\n"
                f"🎉 Get {discount_text} on your next order.\n"
                f"Coupon Code: {coupon.code}\n"
                f"Minimum Order: ₹{int(coupon.minimum_order_amount)}\n"
                f"Valid Until: {coupon.valid_until.strftime('%d %b %Y')}\n\n"
                f"Shop now at {site_url}/\n\n"
                f"Warm regards,\nAI Store Team"
            )



            try:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=plain_message,
                    from_email=from_email,
                    to=[user.email]
                )
                msg.attach_alternative(html_message, "text/html")
                msg.send(fail_silently=False)
                sent_count += 1
                logger.info(f"Email sent: Broadcast delivered to {user.email}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Email failed: Could not send broadcast to {user.email}: {e}")

        # 6. Log the result
        logger.info(
            f"Task completed: Coupon '{coupon.code}' broadcast finished. "
            f"Successful: {sent_count}, Failed: {failed_count}."
        )
        return f"Broadcast finished: {sent_count} successful, {failed_count} failed."

    except Exception as exc:
        logger.error(f"Task error: Failed to execute coupon broadcast for coupon {coupon_id}: {exc}")
        raise self.retry(exc=exc)




def validate_user_email(email):
    """
    Validates email format strictly.
    Returns (is_valid: bool, error_message: str)
    """
    
    if not email:
        return False, "Email address is required."

    email = email.strip()

    try:
        validate_email(email)
    except ValidationError:
        return False, "Please enter a valid email address format (e.g., user@example.com)."

    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]{2,}$"
    if not re.match(email_regex, email):
        return False, "Please enter a valid email address with a proper domain."

    return True, ""


def generate_and_send_otp(user, purpose="registration"):
    """
    Generates a 6-digit OTP stored directly in user.temp_otp (valid for 10 minutes)
    and dispatches it in the background via Celery.
    """
    # 1. Generate 6-digit random code
    otp_code = f"{random.randint(100000, 999999)}"

    # 2. Save directly on user model
    user.temp_otp = otp_code
    user.otp_created_at = timezone.now()
    user.save(update_fields=["temp_otp", "otp_created_at"])

    user_display = user.first_name if user.first_name else user.username

    # 3. Dispatch Celery task to send email asynchronously in the background
    send_otp_email_task.delay(user.email, user_display, otp_code, purpose)

    return True