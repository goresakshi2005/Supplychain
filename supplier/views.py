from .models import SupplierReview, Bid
from .forms import ReviewForm
from django.shortcuts import get_object_or_404, redirect
from negotiation.forms import CounterOfferForm
from negotiation.models import Negotiation, NegotiationMessage
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from .forms import SupplierRegistrationForm, SupplierLoginForm, BidForm, ReviewForm
from .models import Supplier, Bid, SupplierReview
from django.contrib.auth.models import User
from manufacturer.models import QuoteRequest, Manufacturer
from django.contrib import messages

# Add at the top
from django.conf import settings
from utils.email import send_email
from django.db.models import Avg
from django.contrib.auth.decorators import login_required
from django.utils import timezone

import json
import math
import requests
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from geopy.distance import great_circle
from geopy.geocoders import Nominatim
from django.conf import settings
from collections import defaultdict


def supplier_register(request):
    if request.method == 'POST':
        form = SupplierRegistrationForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password1']
            )

            supplier = Supplier.objects.create(
                user=user,
                first_name=form.cleaned_data['first_name'],
                last_name=form.cleaned_data['last_name'],
                company_name=form.cleaned_data['company_name'],
                city=form.cleaned_data['city'],
                state=form.cleaned_data['state'],
                business_type=form.cleaned_data['business_type'],
                website=form.cleaned_data['website'],
                phone_number=form.cleaned_data['phone_number'],
                key_services=form.cleaned_data['key_services'],
                wallet_address=form.cleaned_data['wallet_address']
            )

            # Send welcome email
            send_email(
                subject="Your Supplier Account Has Been Created",
                to_email=user.email,
                template_name="emails/account_created_supplier.html",
                context={
                    'supplier': supplier,
                    'user': user
                }
            )

            # Log the user in after registration
            authenticated_user = authenticate(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password1']
            )
            if authenticated_user is not None:
                login(request, authenticated_user)

            messages.success(request, 'Supplier registered successfully!')
            # Redirect to dashboard after successful registration
            return redirect('supplier_dashboard')
    else:
        form = SupplierRegistrationForm()
    return render(request, 'supplier/register.html', {'form': form})


def supplier_login(request):
    if request.method == 'POST':
        form = SupplierLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                # Check if this user is a supplier
                try:
                    supplier = Supplier.objects.get(user=user)
                    login(request, user)
                    return redirect('supplier_dashboard')
                except Supplier.DoesNotExist:
                    form.add_error(
                        None, "This account is not registered as a supplier")
    else:
        form = SupplierLoginForm()
    return render(request, 'supplier/login.html', {'form': form})

# supplier/views.py


def supplier_dashboard(request):
    if not request.user.is_authenticated:
        return redirect('supplier_login')

    try:
        supplier = Supplier.objects.get(user=request.user)
        open_quotes = QuoteRequest.objects.filter(
            status='open').order_by('-created_at')
        reviews = supplier.reviews.all()
        average_rating = reviews.aggregate(Avg('rating'))['rating__avg']
        negotiations = Negotiation.objects.filter(
            bid__supplier=supplier,
            status='active'
        ).select_related('bid', 'bid__quote')[:5]  # Show only 5 most recent

        # Category filtering
        category_filter = request.GET.get('category')
        if category_filter:
            open_quotes = open_quotes.filter(category=category_filter)

        your_bids = Bid.objects.filter(
            supplier=supplier).select_related('quote')

        return render(request, 'supplier/dashboard.html', {
            'supplier': supplier,
            'open_quotes': open_quotes,
            'your_bids': your_bids,
            'negotiations': negotiations,
            'categories': QuoteRequest.objects.values_list('category', flat=True).distinct(),
            'current_category': category_filter,
            'now': timezone.now(),
            'average_rating': average_rating,
            'review_count': reviews.count()
        })
    except Supplier.DoesNotExist:
        return redirect('supplier_login')


# Update submit_bid function
def submit_bid(request, quote_id):
    if not request.user.is_authenticated:
        return redirect('supplier_login')

    supplier = get_object_or_404(Supplier, user=request.user)
    quote = get_object_or_404(QuoteRequest, id=quote_id, status='open')

    if request.method == 'POST':
        form = BidForm(request.POST)
        if form.is_valid():
            bid = Bid.objects.create(
                supplier=supplier,
                quote=quote,
                bid_amount=form.cleaned_data['bid_amount'],
                delivery_time=form.cleaned_data['delivery_time'],
                comments=form.cleaned_data['comments']
            )

            # Send bid confirmation to supplier
            send_email(
                subject=f"Your Bid for {quote.product} Has Been Submitted",
                to_email=request.user.email,
                template_name="emails/bid_submitted.html",
                context={
                    'supplier': supplier,
                    'quote': quote,
                    'bid': bid
                }
            )

            # Send notification to manufacturer
            send_email(
                subject=f"New Bid Received for {quote.product}",
                to_email=quote.manufacturer.user.email,
                template_name="emails/new_bid_received.html",
                context={
                    'manufacturer': quote.manufacturer,
                    'supplier': supplier,
                    'quote': quote,
                    'bid': bid
                }
            )

            messages.success(
                request, 'Your bid has been submitted successfully!')
            return redirect('supplier_dashboard')
    else:
        form = BidForm()

    return render(request, 'supplier/submit_bid.html', {
        'form': form,
        'quote': quote,
        'supplier': supplier
    })


def view_profile(request):
    if not request.user.is_authenticated:
        return redirect('supplier_login')

    supplier = Supplier.objects.get(user=request.user)
    reviews = supplier.reviews.all()
    # average_rating = reviews.aggregate(models.Avg('rating'))['rating__avg']
    average_rating = reviews.aggregate(Avg('rating'))['rating__avg']

    return render(request, 'supplier/profile.html', {
        'supplier': supplier,
        'reviews': reviews,
        'average_rating': average_rating,
        'review_count': reviews.count()
    })


def edit_profile(request):
    if not request.user.is_authenticated:
        return redirect('supplier_login')

    supplier = Supplier.objects.get(user=request.user)

    if request.method == 'POST':
        # Update basic fields (no image handling)
        supplier.first_name = request.POST.get(
            'first_name', supplier.first_name)
        supplier.last_name = request.POST.get('last_name', supplier.last_name)
        supplier.company_name = request.POST.get(
            'company_name', supplier.company_name)
        supplier.city = request.POST.get('city', supplier.city)
        supplier.state = request.POST.get('state', supplier.state)
        supplier.business_type = request.POST.get(
            'business_type', supplier.business_type)
        supplier.website = request.POST.get('website', supplier.website)
        supplier.phone_number = request.POST.get(
            'phone_number', supplier.phone_number)
        supplier.key_services = request.POST.get(
            'key_services', supplier.key_services)
        supplier.save()

        messages.success(request, 'Profile updated successfully!')
        return redirect('supplier_profile')

    return render(request, 'supplier/edit_profile.html', {
        'supplier': supplier
    })


def view_manufacturer_profile(request, manufacturer_id):
    if not request.user.is_authenticated:
        return redirect('supplier_login')

    try:
        supplier = Supplier.objects.get(user=request.user)
        manufacturer = Manufacturer.objects.get(id=manufacturer_id)
        quote_id = request.GET.get('quote_id')  # Get from URL parameter
        return render(request, 'supplier/manufacturer_profile.html', {
            'manufacturer': manufacturer,
            'supplier': supplier,
            'quote_id': quote_id
        })
    except Manufacturer.DoesNotExist:
        messages.error(request, "Manufacturer not found")
        return redirect('supplier_dashboard')


def supplier_negotiations(request):
    if not request.user.is_authenticated:
        return redirect('supplier_login')

    supplier = get_object_or_404(Supplier, user=request.user)
    negotiations = Negotiation.objects.filter(
        bid__supplier=supplier).select_related('bid', 'bid__quote')

    return render(request, 'supplier/negotiations.html', {
        'supplier': supplier,
        'negotiations': negotiations,
        'now': timezone.now()
    })


def supplier_view_negotiation(request, negotiation_id):
    if not request.user.is_authenticated:
        return redirect('supplier_login')

    negotiation = get_object_or_404(Negotiation, id=negotiation_id)
    bid = negotiation.bid

    # Check if user is the supplier for this bid
    if bid.supplier.user != request.user:
        messages.error(
            request, "You don't have permission to view this negotiation")
        return redirect('supplier_dashboard')

    # Mark unread messages as read
    negotiation.messages.filter(is_read=False).exclude(
        sender=request.user).update(is_read=True)

    if request.method == 'POST':
        form = CounterOfferForm(request.POST)
        if form.is_valid():
            # Create new message with counter offer
            message = NegotiationMessage.objects.create(
                negotiation=negotiation,
                sender=request.user,
                message=form.cleaned_data['message'],
                counter_amount=form.cleaned_data['counter_amount'],
                counter_delivery_time=form.cleaned_data['counter_delivery_time']
            )

            # Notify manufacturer
            send_email(
                subject=f"Counter Offer Received for {bid.quote.product}",
                to_email=bid.quote.manufacturer.user.email,
                template_name="emails/counter_offer_received.html",
                context={
                    'manufacturer': bid.quote.manufacturer,
                    'supplier': bid.supplier,
                    'quote': bid.quote,
                    'bid': bid,
                    'negotiation': negotiation,
                    'message': message
                }
            )

            messages.success(request, 'Counter offer submitted successfully!')
            return redirect('supplier_view_negotiation', negotiation_id=negotiation.id)
    else:
        form = CounterOfferForm()

    return render(request, 'supplier/view_negotiation.html', {
        'negotiation': negotiation,
        'bid': bid,
        'messages': negotiation.messages.all().order_by('created_at'),
        'form': form,
        'now': timezone.now()
    })


# Add to supplier/views.py


def submit_review(request, bid_id):
    if not request.user.is_authenticated or not hasattr(request.user, 'manufacturer'):
        return redirect('manufacturer_login')

    bid = get_object_or_404(Bid, id=bid_id)

    # Check if the current user is the manufacturer who accepted this bid
    if bid.quote.manufacturer.user != request.user or bid.status != 'accepted':
        messages.error(request, "You can't review this bid")
        return redirect('manufacturer_dashboard')

    # Check if review already exists
    if hasattr(bid, 'review'):
        messages.info(
            request, "You've already reviewed this supplier for this bid")
        return redirect('manufacturer_dashboard')

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.supplier = bid.supplier
            review.manufacturer = bid.quote.manufacturer
            review.bid = bid
            review.save()

            # Mark that feedback has been given
            bid.feedback_given = True
            bid.save()

            # Send email notification to supplier
            send_email(
                subject=f"New Review Received from {review.manufacturer.company_name}",
                to_email=review.supplier.user.email,
                template_name="emails/new_review_received.html",
                context={
                    'supplier': review.supplier,
                    'manufacturer': review.manufacturer,
                    'review': review,
                    'bid': bid
                }
            )

            messages.success(request, 'Thank you for your feedback!')
            # return redirect('manufacturer_dashboard')
            return redirect('manufacturer_quote_history')
    else:
        form = ReviewForm()

    return render(request, 'supplier/submit_review.html', {
        'form': form,
        'bid': bid,
        'supplier': bid.supplier
    })


@csrf_exempt
@require_POST
def calculate_route(request):
    try:
        data = json.loads(request.body)

        # Get locations from request
        supplier_city = data['supplier_city']
        supplier_state = data['supplier_state']
        manufacturer_city = data['manufacturer_city']
        manufacturer_state = data['manufacturer_state']
        transport_mode = data['transport_mode']
        lead_time = float(data['lead_time'])

        # Initialize geocoder
        geolocator = Nominatim(user_agent="supply_chain_app")

        # Get coordinates for both locations
        def get_coords(city, state):
            location = geolocator.geocode(f"{city}, {state}", timeout=10)
            if not location:
                raise ValueError(f"Could not locate {city}, {state}")
            return (location.latitude, location.longitude)

        supplier_coords = get_coords(supplier_city, supplier_state)
        manufacturer_coords = get_coords(manufacturer_city, manufacturer_state)

        if transport_mode == 'road':
            # Calculate detailed road route using OpenRouteService API
            headers = {
                'Authorization': settings.OPENROUTE_API_KEY,
                'Content-Type': 'application/json'
            }
            body = {
                "coordinates": [
                    [supplier_coords[1], supplier_coords[0]],  # lon,lat format
                    [manufacturer_coords[1], manufacturer_coords[0]]
                ],
                "instructions": "true",
                "geometry": "true"
            }

            response = requests.post(
                'https://api.openrouteservice.org/v2/directions/driving-car',
                headers=headers,
                json=body,
                timeout=15
            )

            if response.status_code != 200:
                raise ValueError(f"Road route error: {response.text}")

            route_data = response.json()
            distance_km = route_data['routes'][0]['summary']['distance'] / 1000
            duration_hours = route_data['routes'][0]['summary']['duration'] / 3600
            duration_days = duration_hours / 24

            # Process detailed route steps
            steps = route_data['routes'][0]['segments'][0]['steps']
            route_steps = []
            step_types = defaultdict(int)

            for step in steps:
                instruction = step['instruction'].replace('Head', 'Continue')
                distance = step['distance']

                # Classify step type
                if 'highway' in instruction.lower() or 'motorway' in instruction.lower():
                    step_type = 'highway'
                elif 'left' in instruction.lower():
                    step_type = 'left_turn'
                elif 'right' in instruction.lower():
                    step_type = 'right_turn'
                elif 'roundabout' in instruction.lower():
                    step_type = 'roundabout'
                else:
                    step_type = 'regular'

                step_types[step_type] += 1

                route_steps.append({
                    'instruction': instruction,
                    'distance': f"{distance}m",
                    'type': step_type
                })

            # Generate route summary
            highway_percentage = (step_types['highway'] / len(steps)) * 100
            route_summary = (
                f"Route includes {len(steps)} steps: "
                f"{step_types['highway']} highway sections ({highway_percentage:.0f}%), "
                f"{step_types['left_turn']} left turns, "
                f"{step_types['right_turn']} right turns"
            )

            # Generate detailed directions
            detailed_directions = "\n".join(
                [f"{i+1}. {step['instruction']} ({step['distance']})"
                 for i, step in enumerate(route_steps)])

            total_days = lead_time + duration_days

            return JsonResponse({
                'success': True,
                'mode': 'road',
                'distance': round(distance_km, 1),
                'transit_time': f"{round(duration_hours, 1)} hours",
                'route_summary': route_summary,
                'detailed_directions': detailed_directions,
                'total_steps': len(steps),
                'highway_percentage': round(highway_percentage),
                'total_days': round(total_days, 1),
                'delivery_days': math.ceil(total_days)
            })

        elif transport_mode == 'air':
            # Calculate air distance and estimate time (kept simple)
            distance_km = great_circle(supplier_coords, manufacturer_coords).km
            flight_hours = distance_km / 900  # Average 900 km/h airspeed
            handling_days = 1  # Standard 1 day for air freight handling
            total_transit_days = (flight_hours / 24) + handling_days

            total_days = lead_time + total_transit_days

            return JsonResponse({
                'success': True,
                'mode': 'air',
                'distance': round(distance_km, 1),
                'transit_time': f"{round(flight_hours, 1)} hours flight + {handling_days} day handling",
                'route_description': f"{supplier_city} Airport → {manufacturer_city} Airport",
                'total_days': round(total_days, 1),
                'delivery_days': math.ceil(total_days)
            })

        else:
            raise ValueError("Invalid transport mode")

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
