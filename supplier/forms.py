from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from manufacturer.models import QuoteRequest

class SupplierRegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True)
    last_name = forms.CharField(max_length=100, required=True)
    company_name = forms.CharField(max_length=200, required=True)
    city = forms.CharField(max_length=100, required=True)
    state = forms.CharField(max_length=100, required=True)
    business_type = forms.CharField(max_length=100, required=True)
    website = forms.URLField(required=False)
    phone_number = forms.CharField(max_length=20, required=True)
    key_services = forms.CharField(widget=forms.Textarea, required=True)
    email = forms.EmailField(required=True)
    wallet_address = forms.CharField(max_length=42, required=True, 
                                   label="Ethereum Wallet Address (0x...)")

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2',
                  'first_name', 'last_name', 'company_name', 'city', 
                  'state', 'business_type', 'website', 'phone_number', 
                  'key_services', 'wallet_address')

class SupplierLoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)


class BidForm(forms.Form):
    bid_amount = forms.DecimalField(label="Your Price", min_value=0)
    delivery_time = forms.IntegerField(label="Delivery Time (days)", min_value=1)
    comments = forms.CharField(widget=forms.Textarea, required=False)


# Add to supplier/forms.py
from django import forms
from .models import SupplierReview

from django import forms

class ReviewForm(forms.ModelForm):
    # Define rating choices (1-5 with labels)
    RATING_CHOICES = [
        (1, 'Poor'),
        (2, 'Fair'),
        (3, 'Good'),
        (4, 'Very Good'),
        (5, 'Excellent'),
    ]
    
    # Override the rating field to use RadioSelect with our choices
    rating = forms.ChoiceField(
        choices=RATING_CHOICES,
        widget=forms.RadioSelect,
        required=True
    )
    
    class Meta:
        model = SupplierReview
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 4}),
        }