from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import render
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import gettext as _

User = get_user_model()


def password_reset_confirm(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(str(uidb64)).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == "POST":
            password = request.POST.get("password")
            password2 = request.POST.get("password2")
            if not password or not password2:
                return render(
                    request,
                    "user/password_reset_confirm.html",
                    {
                        "error": _("Please fill in both password fields."),
                        "validlink": True,
                    },
                )
            if password != password2:
                return render(
                    request,
                    "user/password_reset_confirm.html",
                    {"error": _("Passwords do not match."), "validlink": True},
                )
            user.password = make_password(password)
            user.save()
            return render(
                request,
                "user/password_reset_confirm.html",
                {
                    "success": _("Your password has been reset. You can now log in."),
                    "validlink": False,
                },
            )
        return render(request, "user/password_reset_confirm.html", {"validlink": True})
    else:
        return render(
            request,
            "user/password_reset_confirm.html",
            {
                "error": _("The reset link is invalid or has expired."),
                "validlink": False,
            },
        )
