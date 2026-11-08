from django.http import HttpResponse
from django.shortcuts import render
from .models import SchoolProfile
from django.contrib.auth.decorators import login_required


@login_required
def home(request):
    return render(request, 'home.html', {})

def school_css(request):
    profile = SchoolProfile.get()
    css = (
        ":root {\n"
        f"  --school-primary: {profile.primary_colour};\n"
        f"  --school-accent: {profile.accent_colour};\n"
        "}\n"
        ".navbar.bg-school { background-color: var(--school-primary) !important; }\n"
        ".btn-school { background-color: var(--school-primary); color: #fff; border: none; }\n"
        ".btn-school:hover { opacity: 0.9; color: #fff; }\n"
    )
    return HttpResponse(css, content_type='text/css')