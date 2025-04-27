from django.shortcuts import render, redirect, get_object_or_404
import uuid
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.http import JsonResponse, Http404
from .models import *
from .utils import verify_dns_settings, request_ssl_certificate, auto_generate_seo_content
import json
from django.utils.text import slugify
import logging
from django.utils import timezone
import shutil
import os
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
import dns.resolver

# Set up logging
logger = logging.getLogger(__name__)

# Create your views here.

@login_required
def dashboard(request):
    """Dashboard view showing all websites of the current user"""
    # Get the current user directly from request.user
    user = request.user
    
    if not user or not user.is_authenticated:
        messages.warning(request, 'Please log in to access the dashboard')
        return redirect('login')
    
    # Get all websites for the current user
    websites = Website.objects.filter(user=user).order_by('-updated_at')
    
    # Fix any websites with missing public slugs
    for website in websites:
        if not website.public_slug or website.public_slug == 'None':
            website.save()  # This will trigger the save method to generate a slug
    
    # Get domains associated with the user's websites
    domains = CustomDomain.objects.filter(website__user=user)
    
    websites_data = []
    for website in websites:
        # Get pages count
        pages_count = website.get_pages().count()
        
        # Get associated domains
        site_domains = domains.filter(website=website)
        
        # Add to the data list
        websites_data.append({
            'website': website,
            'pages_count': pages_count,
            'domains': site_domains,
            'public_url': request.build_absolute_uri(website.get_public_url())
        })
    
    # Check if this is a new user or if they're seeing the dashboard for the first time
    show_setup_guide = False
    if not request.session.get('dashboard_visited', False):
        show_setup_guide = True
        request.session['dashboard_visited'] = True
    
    return render(request, 'website/dashboard.html', {
        'websites_data': websites_data,
        'show_setup_guide': show_setup_guide
    })

@login_required
def domain_settings(request):
    websites = Website.objects.filter(user=request.user)
    domains = CustomDomain.objects.filter(website__user=request.user)
    
    # Default to first website if none selected
    selected_website_id = None
    if websites.exists():
        selected_website_id = request.session.get('selected_website_id')
        if not selected_website_id:
            selected_website_id = websites.first().id
            request.session['selected_website_id'] = selected_website_id
    
    if request.method == 'POST':
        domain = request.POST.get('domain')
        website_id = request.POST.get('website_id')
        
        # Update selected website in session
        if website_id:
            request.session['selected_website_id'] = int(website_id)
            selected_website_id = int(website_id)
        
        try:
            # Validate domain format
            URLValidator()(f"https://{domain}")
            
            # Check if domain is already registered
            if CustomDomain.objects.filter(domain=domain).exists():
                messages.error(request, 'This domain is already registered.')
                return redirect('domain_settings')
            
            # Generate verification code
            verification_code = str(uuid.uuid4())
            
            if website_id:
                # Create new domain record
                custom_domain = CustomDomain.objects.create(
                    website_id=website_id,
                    domain=domain,
                    verification_code=verification_code,
                    verification_status='pending',
                    ssl_status=False
                )
                
                messages.success(request, 'Domain added successfully. Please configure DNS settings.')
                return redirect('domain_verification', domain_id=custom_domain.id)
            else:
                messages.error(request, 'Please select a website to add the domain to.')
                return redirect('domain_settings')
            
        except ValidationError:
            messages.error(request, 'Please enter a valid domain name.')
    
    context = {
        'websites': websites,
        'domains': domains,
        'selected_website_id': selected_website_id
    }
    
    return render(request, 'website/domain_settings.html', context)

@login_required
def domain_verification(request, domain_id):
    """View for verifying a custom domain"""
    domain = get_object_or_404(CustomDomain, id=domain_id, website__user=request.user)
    
    # Check if domain is already verified
    if domain.verification_status == 'verified':
        messages.info(request, f'Domain {domain.domain} is already verified.')
        return render(request, 'website/domain_verification.html', {'domain': domain, 'already_verified': True})
    
    if request.method == 'POST':
        # Before verification, check if there are recent verification attempts
        recent_attempts = DomainLog.objects.filter(
            domain=domain.domain, 
            created_at__gte=timezone.now() - timezone.timedelta(minutes=2)
        ).count()
        
        # If there are too many recent attempts, ask user to wait
        if recent_attempts > 5:
            messages.warning(request, 'Too many verification attempts. Please wait a few minutes before trying again.')
            return render(request, 'website/domain_verification.html', {'domain': domain, 'too_many_attempts': True})
        
        # Verify DNS settings
        verification_result = verify_dns_settings(domain.domain, domain.verification_code)
        
        if verification_result:
            # Update domain status
            domain.verification_status = 'verified'
            domain.save()
            
            # Request SSL certificate in the background
            try:
                request_ssl_certificate(domain.domain)
                ssl_message = "SSL certificate request initiated. This may take up to 30 minutes to complete."
            except Exception as e:
                ssl_message = f"Domain verified, but there was an issue requesting SSL: {str(e)}"
            
            messages.success(request, f'Domain {domain.domain} verified successfully! {ssl_message}')
            return redirect('domain_settings')
        else:
            # Check specific DNS records to provide better feedback
            verification_issues = []
            
            # Check TXT record
            try:
                txt_records = dns.resolver.resolve(domain.domain, 'TXT')
                txt_found = False
                for record in txt_records:
                    if f"verification={domain.verification_code}" in str(record):
                        txt_found = True
                        break
                if not txt_found:
                    verification_issues.append("The TXT record with your verification code was not found.")
            except Exception:
                verification_issues.append("No TXT records found. Please add the TXT record with your verification code.")
            
            # Check A record
            try:
                a_records = dns.resolver.resolve(domain.domain, 'A')
                a_found = False
                for record in a_records:
                    if str(record) == '89.116.20.128':  # Replace with your server's IP
                        a_found = True
                        break
                if not a_found:
                    verification_issues.append("The A record doesn't point to our server (89.116.20.128).")
            except Exception:
                verification_issues.append("No A record found. Please add an A record pointing to our server.")
            
            # If no specific issues were found but verification still failed
            if not verification_issues:
                verification_issues.append("DNS verification failed. Please check your DNS settings or wait longer for DNS propagation.")
            
            messages.error(request, 'Domain verification failed')
            return render(request, 'website/domain_verification.html', {
                'domain': domain,
                'verification_failed': True,
                'verification_issues': verification_issues
            })
    
    return render(request, 'website/domain_verification.html', {'domain': domain})

@login_required
def delete_domain(request, domain_id):
    """View for deleting a custom domain"""
    try:
        # Ensure the domain belongs to a website owned by the user
        domain = CustomDomain.objects.get(id=domain_id, website__user=request.user)
        
        # Store domain name for success message
        domain_name = domain.domain
        
        # Delete the domain
        domain.delete()
        
        messages.success(request, f'Domain "{domain_name}" has been deleted successfully!')
    except CustomDomain.DoesNotExist:
        messages.error(request, 'Domain not found or you do not have permission to delete it.')
    
    return redirect('domain_settings')

@login_required
def select_template(request):
    # Get all active templates
    all_templates = WebsiteTemplate.objects.filter(is_active=True)
    
    # Get templates already used by the user
    used_templates = Website.objects.filter(user=request.user).values_list('template_id', flat=True)
    
    # Filter out templates that are already in use by the user
    available_templates = all_templates.exclude(id__in=used_templates)
    
    # Add warning message if user has already used some templates
    if used_templates.exists():
        messages.info(request, "You can only use each template once. Templates you've already used are not shown.")
    
    return render(request, 'website/select_template.html', {
        'templates': available_templates
    })

@login_required
def create_website(request, template_id):
    template = get_object_or_404(WebsiteTemplate, id=template_id, is_active=True)
    
    # Check if user has already used this template
    if Website.objects.filter(user=request.user, template=template).exists():
        messages.error(request, "You have already used this template. Please choose a different one.")
        return redirect('select_template')
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            # Extract content data properly
            content_data = data.get('content', {})
            
            # Create the website with the submitted content
            website = Website.objects.create(
                user=request.user,
                template=template,
                content=content_data
            )
            
            # Generate public slug and ensure it's saved
            if not website.public_slug:
                base_slug = slugify(f"{request.user.username}-site")
                unique_id = str(uuid.uuid4())[:8]
                website.public_slug = f"{base_slug}-{unique_id}"
                website.save()
            
            # Apply automatic SEO improvements
            auto_generate_seo_content(website, request)
            
            # Create a default homepage
            WebsitePage.objects.create(
                website=website,
                title='Home',
                slug='home',
                template_file='home.html',
                is_homepage=True,
                order=0,
                content=content_data
            )
            
            # Build absolute URL for the public website
            public_url = request.build_absolute_uri(website.get_public_url())
            
            # Return success response with all needed information
            return JsonResponse({
                'status': 'success',
                'message': 'Website created successfully',
                'website_id': website.id,
                'public_url': public_url,
                'redirect_url': reverse('edit_website', args=[website.id])
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
            
    # For GET requests, return the create page
    return render(request, 'website/create_website.html', {
        'template': template
    })

@login_required
def edit_website(request, website_id):
    """View for editing website content"""
    website = get_object_or_404(Website, id=website_id, user=request.user)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.POST.get('content', '{}'))
            
            # Extract contact information
            contact_info = {
                'mobile_number': data.get('mobile_number', ''),
                'contact_email': data.get('contact_email', ''),
                'address': data.get('address', ''),
                'map_location': data.get('map_location', '')
            }
            
            # Update the website content
            website.content.update(data)
            
            # Update contact information
            if 'contact_info' not in website.content:
                website.content['contact_info'] = {}
            website.content['contact_info'].update(contact_info)
            
            # Save the website
            website.save(force_update=True)
            
            return JsonResponse({
                'status': 'success',
                'message': 'Website content updated successfully',
                'content': website.content
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid JSON data provided'
            }, status=400)
        except Exception as e:
            logger.error(f"Error updating website content: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'An error occurred while updating the website content'
            }, status=500)
    
    # For GET requests, prepare the context
    context = {
        'website': website,
        'schema': website.template.content_schema if website.template else {},
    }
    
    return render(request, 'website/edit_website.html', context)

@login_required
def preview_website(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    
    # Ensure required fields exist in website content
    required_fields = [
        'meta_description', 'meta_keywords', 'site_name', 
        'hero_title', 'hero_subtitle', 'hero_button',
        'features_title', 'features_subtitle', 'features',
        'about_title', 'about_content', 'about_image', 'about_button',
        'cta_title', 'cta_subtitle', 'cta_main_button'
    ]
    
    # Copy description to meta_description if available
    if 'meta_description' not in website.content and 'description' in website.content:
        website.content['meta_description'] = website.content['description']
    
    # Ensure websiteName is copied to site_name if needed
    if 'site_name' not in website.content and 'websiteName' in website.content:
        website.content['site_name'] = website.content['websiteName']
    
    # Set default empty values for all required fields if missing
    for field in required_fields:
        if field not in website.content:
            if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                website.content[field] = {'url': '#', 'label': 'Learn More'}
            elif field == 'features':
                website.content[field] = [
                    {
                        'icon': 'palette',
                        'title': 'Beautiful Design',
                        'description': 'Modern and elegant designs that capture attention and create memorable experiences.'
                    },
                    {
                        'icon': 'mobile-alt',
                        'title': 'Responsive Layout',
                        'description': 'Our websites look amazing on all devices, from desktops to smartphones.'
                    },
                    {
                        'icon': 'bolt',
                        'title': 'Performance Optimized',
                        'description': 'Fast loading times and smooth performance for the best user experience.'
                    }
                ]
            elif field == 'about_image':
                website.content[field] = 'https://via.placeholder.com/600x400'
            else:
                website.content[field] = ""
    
    homepage = website.pages.filter(is_homepage=True).first()
    
    if homepage:
        # Ensure required fields exist in page content
        if homepage.content is None:
            homepage.content = {}
            
        # Set default empty values for all required fields if missing in page content
        for field in required_fields:
            if field not in homepage.content:
                if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                    homepage.content[field] = {'url': '#', 'label': 'Learn More'}
                elif field == 'features':
                    homepage.content[field] = [
                        {
                            'icon': 'palette',
                            'title': 'Beautiful Design',
                            'description': 'Modern and elegant designs that capture attention and create memorable experiences.'
                        },
                        {
                            'icon': 'mobile-alt',
                            'title': 'Responsive Layout',
                            'description': 'Our websites look amazing on all devices, from desktops to smartphones.'
                        },
                        {
                            'icon': 'bolt',
                            'title': 'Performance Optimized',
                            'description': 'Fast loading times and smooth performance for the best user experience.'
                        }
                    ]
                elif field == 'about_image':
                    homepage.content[field] = 'https://via.placeholder.com/600x400'
                else:
                    homepage.content[field] = ""
        
        # Use template path with forward slashes for Django template loader
        template_path = f"{website.template.template_path.strip('/')}/{homepage.template_file}"
        return render(request, template_path, {
            'website': website,
            'page': homepage,
            'content': homepage.content,
            'global_content': website.content,
            'default_banners': [
                {
                    'image': 'https://via.placeholder.com/1920x1080',
                    'title': 'Welcome to Your Store',
                    'description': 'Discover amazing products at great prices',
                    'button_text': 'Shop Now',
                    'button_url': '/shop'
                }
            ]
        })
    else:
        # Use template path with forward slashes for Django template loader
        template_path = f"{website.template.template_path.strip('/')}/home.html"
        return render(request, template_path, {
            'website': website,
            'content': website.content,
            'default_banners': [
                {
                    'image': 'https://via.placeholder.com/1920x1080',
                    'title': 'Welcome to Your Store',
                    'description': 'Discover amazing products at great prices',
                    'button_text': 'Shop Now',
                    'button_url': '/shop'
                }
            ]
        })

@login_required
def manage_pages(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    pages = website.get_pages()
    
    return render(request, 'website/manage_pages.html', {
        'website': website,
        'pages': pages
    })

@login_required
def create_page(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        slug = request.POST.get('slug') or slugify(title)
        template_file = request.POST.get('template_file')
        is_homepage = request.POST.get('is_homepage') == 'on'
        
        # Get available templates
        template_pages = website.template.get_template_pages()
        available_templates = [page['file'] for page in template_pages]
        
        # Validate if the template file is in the available templates
        if template_file not in available_templates:
            messages.error(request, f'Template file {template_file} is not available for this website')
            return redirect('manage_pages', website_id=website.id)
        
        # Check if the slug is unique
        if WebsitePage.objects.filter(website=website, slug=slug).exists():
            messages.error(request, f'A page with slug "{slug}" already exists')
            return redirect('manage_pages', website_id=website.id)
        
        # Create the page
        WebsitePage.objects.create(
            website=website,
            title=title,
            slug=slug,
            template_file=template_file,
            is_homepage=is_homepage,
            order=WebsitePage.objects.filter(website=website).count() + 1
        )
        
        messages.success(request, f'Page "{title}" created successfully!')
        return redirect('manage_pages', website_id=website.id)
    
    # Get available templates from the template directory
    template_pages = website.template.get_template_pages()
    
    return render(request, 'website/create_page.html', {
        'website': website,
        'template_pages': template_pages
    })

@login_required
def edit_page(request, page_id):
    page = get_object_or_404(WebsitePage, id=page_id, website__user=request.user)
    website = page.website
    
    if request.method == 'POST':
        try:
            # Update page metadata
            page.title = request.POST.get('title')
            page.slug = request.POST.get('slug') or slugify(page.title)
            page.template_file = request.POST.get('template_file')
            page.is_homepage = request.POST.get('is_homepage') == 'on'
            
            # Validate template file is in available templates
            template_pages = website.template.get_template_pages()
            available_templates = [page_info['file'] for page_info in template_pages]
            
            if page.template_file not in available_templates:
                messages.error(request, f'Template file {page.template_file} is not available for this website')
                return redirect('edit_page', page_id=page.id)
            
            # Update page content
            content = json.loads(request.POST.get('content', '{}'))
            page.content = content
            
            # Ensure the page is properly saved to the database
            page.save()
            
            messages.success(request, f'Page "{page.title}" updated successfully!')
            return redirect('manage_pages', website_id=website.id)
        except json.JSONDecodeError:
            messages.error(request, 'Invalid content format')
        except Exception as e:
            messages.error(request, f'Error updating page: {str(e)}')
    
    # Get available templates from the template directory
    template_pages = website.template.get_template_pages()
    
    return render(request, 'website/edit_page.html', {
        'website': website,
        'page': page,
        'template_pages': template_pages
    })

@login_required
def delete_page(request, page_id):
    page = get_object_or_404(WebsitePage, id=page_id, website__user=request.user)
    website_id = page.website.id
    
    if request.method == 'POST':
        # Don't allow deleting the last page
        if WebsitePage.objects.filter(website=page.website).count() <= 1:
            messages.error(request, 'Cannot delete the only page of the website')
            return redirect('manage_pages', website_id=website_id)
        
        # If deleting homepage, make another page the homepage
        if page.is_homepage:
            new_homepage = WebsitePage.objects.filter(website=page.website).exclude(id=page.id).first()
            if new_homepage:
                new_homepage.is_homepage = True
                new_homepage.save()
        
        page.delete()
        messages.success(request, f'Page "{page.title}" deleted successfully!')
    
    return redirect('manage_pages', website_id=website_id)

@login_required
def reorder_pages(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    
    if request.method == 'POST':
        try:
            page_order = json.loads(request.body).get('page_order', [])
            
            # Update the order of each page
            for index, page_id in enumerate(page_order):
                WebsitePage.objects.filter(id=page_id, website=website).update(order=index)
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)

@login_required
def home(request):
    website = None
    if hasattr(request, 'website'):
        website = request.website
    else:
        # For development/preview, get the first website of the logged-in user
        if request.user.is_authenticated:
            website = Website.objects.filter(user=request.user).first()
    
    if website:
        # Ensure required fields exist in website content
        required_fields = [
            'meta_description', 'meta_keywords', 'site_name', 
            'hero_title', 'hero_subtitle', 'hero_button',
            'features_title', 'features_subtitle', 'features',
            'about_title', 'about_content', 'about_image', 'about_button',
            'cta_title', 'cta_subtitle', 'cta_main_button'
        ]
        
        # Copy description to meta_description if available
        if 'meta_description' not in website.content and 'description' in website.content:
            website.content['meta_description'] = website.content['description']
        
        # Ensure websiteName is copied to site_name if needed
        if 'site_name' not in website.content and 'websiteName' in website.content:
            website.content['site_name'] = website.content['websiteName']
        
        # Set default empty values for all required fields if missing
        for field in required_fields:
            if field not in website.content:
                if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                    website.content[field] = {'url': '#', 'label': 'Learn More'}
                elif field == 'features':
                    website.content[field] = [
                        {
                            'icon': 'palette',
                            'title': 'Beautiful Design',
                            'description': 'Modern and elegant designs that capture attention and create memorable experiences.'
                        },
                        {
                            'icon': 'mobile-alt',
                            'title': 'Responsive Layout',
                            'description': 'Our websites look amazing on all devices, from desktops to smartphones.'
                        },
                        {
                            'icon': 'bolt',
                            'title': 'Performance Optimized',
                            'description': 'Fast loading times and smooth performance for the best user experience.'
                        }
                    ]
                elif field == 'about_image':
                    website.content[field] = 'https://via.placeholder.com/600x400'
                else:
                    website.content[field] = ""
        
        homepage = website.pages.filter(is_homepage=True).first()
        
        if homepage:
            # Ensure required fields exist in page content
            if homepage.content is None:
                homepage.content = {}
                
            # Set default empty values for all required fields if missing in page content
            for field in required_fields:
                if field not in homepage.content:
                    if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                        homepage.content[field] = {'url': '#', 'label': 'Learn More'}
                    elif field == 'features':
                        homepage.content[field] = [
                            {
                                'icon': 'palette',
                                'title': 'Beautiful Design',
                                'description': 'Modern and elegant designs that capture attention and create memorable experiences.'
                            },
                            {
                                'icon': 'mobile-alt',
                                'title': 'Responsive Layout',
                                'description': 'Our websites look amazing on all devices, from desktops to smartphones.'
                            },
                            {
                                'icon': 'bolt',
                                'title': 'Performance Optimized',
                                'description': 'Fast loading times and smooth performance for the best user experience.'
                            }
                        ]
                    elif field == 'about_image':
                        homepage.content[field] = 'https://via.placeholder.com/600x400'
                    else:
                        homepage.content[field] = ""
            
            # Use template path with forward slashes for Django template loader
            template_path = f"{website.template.template_path.strip('/')}/{homepage.template_file}"
            return render(request, template_path, {
                'website': website,
                'page': homepage,
                'content': homepage.content,
                'global_content': website.content,
                'default_banners': [
                    {
                        'image': 'https://via.placeholder.com/1920x1080',
                        'title': 'Welcome to Your Store',
                        'description': 'Discover amazing products at great prices',
                        'button_text': 'Shop Now',
                        'button_url': '/shop'
                    }
                ]
            })
        else:
            # Use template path with forward slashes for Django template loader
            template_path = f"{website.template.template_path.strip('/')}/home.html"
            return render(request, template_path, {
                'website': website,
                'content': website.content,
                'default_banners': [
                    {
                        'image': 'https://via.placeholder.com/1920x1080',
                        'title': 'Welcome to Your Store',
                        'description': 'Discover amazing products at great prices',
                        'button_text': 'Shop Now',
                        'button_url': '/shop'
                    }
                ]
            })
    
    # If no website found, redirect to template selection
    return redirect('select_template')

def about_us(request):
    """Render the about us page using the website template system"""
    # Get the user's website or first website for preview
    website = None
    if hasattr(request, 'website'):
        website = request.website
    elif request.user.is_authenticated:
        website = Website.objects.filter(user=request.user).first()
    
    if not website:
        # Fallback to a default template if no website is found
        return render(request, 'website/template1/about-us.html')
    
    # Ensure required fields exist in website content
    required_fields = [
        'meta_description', 'meta_keywords', 'site_name', 
        'hero_title', 'hero_subtitle', 'hero_button',
        'features_title', 'features_subtitle', 'features',
        'about_title', 'about_content', 'about_image', 'about_button',
        'cta_title', 'cta_subtitle', 'cta_main_button'
    ]
    
    # Copy description to meta_description if available
    if 'meta_description' not in website.content and 'description' in website.content:
        website.content['meta_description'] = website.content['description']
    
    # Ensure websiteName is copied to site_name if needed
    if 'site_name' not in website.content and 'websiteName' in website.content:
        website.content['site_name'] = website.content['websiteName']
    
    # Set default empty values for all required fields if missing
    for field in required_fields:
        if field not in website.content:
            if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                website.content[field] = {'url': '#', 'label': 'Learn More'}
            elif field == 'features':
                website.content[field] = [
                    {
                        'icon': 'palette',
                        'title': 'Beautiful Design',
                        'description': 'Modern and elegant designs that capture attention and create memorable experiences.'
                    },
                    {
                        'icon': 'mobile-alt',
                        'title': 'Responsive Layout',
                        'description': 'Our websites look amazing on all devices, from desktops to smartphones.'
                    },
                    {
                        'icon': 'bolt',
                        'title': 'Performance Optimized',
                        'description': 'Fast loading times and smooth performance for the best user experience.'
                    }
                ]
            elif field == 'about_image':
                website.content[field] = 'https://via.placeholder.com/600x400'
            else:
                website.content[field] = ""
    
    # Try to find the about-us page in the website's pages
    about_page = website.pages.filter(slug='about-us').first()
    
    if about_page:
        # Ensure required fields exist in page content
        if about_page.content is None:
            about_page.content = {}
            
        # Set default empty values for required fields if missing in page content
        for field in required_fields:
            if field not in about_page.content:
                if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                    about_page.content[field] = {'url': '#', 'label': 'Learn More'}
                elif field == 'features':
                    about_page.content[field] = website.content.get('features', [])
                elif field == 'about_image':
                    about_page.content[field] = 'https://via.placeholder.com/600x400'
                else:
                    about_page.content[field] = ""
        
        # Use template path with forward slashes for Django template loader
        template_path = f"{website.template.template_path.strip('/')}/{about_page.template_file}"
        return render(request, template_path, {
            'website': website,
            'page': about_page,
            'content': about_page.content,
            'global_content': website.content,
            'default_banners': [
                {
                    'image': 'https://via.placeholder.com/1920x1080',
                    'title': 'Welcome to Your Store',
                    'description': 'Discover amazing products at great prices',
                    'button_text': 'Shop Now',
                    'button_url': '/shop'
                }
            ]
        })
    else:
        # If no about-us page exists, use the default about-us template from the website's template
        template_path = f"{website.template.template_path.strip('/')}/about-us.html"
        return render(request, template_path, {
            'website': website,
            'content': website.content,
            'page': {'title': 'About Us', 'slug': 'about-us', 'content': {}},
            'default_banners': [
                {
                    'image': 'https://via.placeholder.com/1920x1080',
                    'title': 'Welcome to Your Store',
                    'description': 'Discover amazing products at great prices',
                    'button_text': 'Shop Now',
                    'button_url': '/shop'
                }
            ]
        })

def public_website(request, public_slug):
    """View for public access to a website via its shareable link"""
    # Handle 'None' string as a special case
    if public_slug == 'None':
        raise Http404("Website not found. Invalid public link.")
        
    website = get_object_or_404(Website, public_slug=public_slug)
    
    # Ensure required fields exist in website content
    required_fields = [
        'meta_description', 'meta_keywords', 'site_name', 
        'hero_title', 'hero_subtitle', 'hero_button',
        'features_title', 'features_subtitle', 'features',
        'about_title', 'about_content', 'about_image', 'about_button',
        'cta_title', 'cta_subtitle', 'cta_main_button'
    ]
    
    # Copy description to meta_description if available
    if 'meta_description' not in website.content and 'description' in website.content:
        website.content['meta_description'] = website.content['description']
    
    # Ensure websiteName is copied to site_name if needed
    if 'site_name' not in website.content and 'websiteName' in website.content:
        website.content['site_name'] = website.content['websiteName']
    
    # Set default empty values for all required fields if missing
    for field in required_fields:
        if field not in website.content:
            if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                website.content[field] = {'url': '#', 'label': 'Learn More'}
            elif field == 'features':
                website.content[field] = [
                    {
                        'icon': 'palette',
                        'title': 'Beautiful Design',
                        'description': 'Modern and elegant designs that capture attention and create memorable experiences.'
                    },
                    {
                        'icon': 'mobile-alt',
                        'title': 'Responsive Layout',
                        'description': 'Our websites look amazing on all devices, from desktops to smartphones.'
                    },
                    {
                        'icon': 'bolt',
                        'title': 'Performance Optimized',
                        'description': 'Fast loading times and smooth performance for the best user experience.'
                    }
                ]
            elif field == 'about_image':
                website.content[field] = 'https://via.placeholder.com/600x400'
            else:
                website.content[field] = ""
    
    homepage = website.pages.filter(is_homepage=True).first()
    
    if homepage:
        # Ensure required fields exist in page content
        if homepage.content is None:
            homepage.content = {}
            
        # Set default empty values for all required fields if missing in page content
        for field in required_fields:
            if field not in homepage.content:
                if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                    homepage.content[field] = {'url': '#', 'label': 'Learn More'}
                elif field == 'features':
                    homepage.content[field] = [
                        {
                            'icon': 'palette',
                            'title': 'Beautiful Design',
                            'description': 'Modern and elegant designs that capture attention and create memorable experiences.'
                        },
                        {
                            'icon': 'mobile-alt',
                            'title': 'Responsive Layout',
                            'description': 'Our websites look amazing on all devices, from desktops to smartphones.'
                        },
                        {
                            'icon': 'bolt',
                            'title': 'Performance Optimized',
                            'description': 'Fast loading times and smooth performance for the best user experience.'
                        }
                    ]
                elif field == 'about_image':
                    homepage.content[field] = 'https://via.placeholder.com/600x400'
                else:
                    homepage.content[field] = ""
        
        # Use template path with forward slashes for Django template loader
        template_path = f"{website.template.template_path.strip('/')}/{homepage.template_file}"
        return render(request, template_path, {
            'website': website,
            'page': homepage,
            'content': homepage.content,
            'global_content': website.content,
            'is_public_view': True,
            'default_banners': [
                {
                    'image': 'https://via.placeholder.com/1920x1080',
                    'title': 'Welcome to Your Store',
                    'description': 'Discover amazing products at great prices',
                    'button_text': 'Shop Now',
                    'button_url': '/shop'
                }
            ]
        })
    else:
        # Use template path with forward slashes for Django template loader
        template_path = f"{website.template.template_path.strip('/')}/home.html"
        return render(request, template_path, {
            'website': website,
            'content': website.content,
            'is_public_view': True,
            'default_banners': [
                {
                    'image': 'https://via.placeholder.com/1920x1080',
                    'title': 'Welcome to Your Store',
                    'description': 'Discover amazing products at great prices',
                    'button_text': 'Shop Now',
                    'button_url': '/shop'
                }
            ]
        })

def public_website_page(request, public_slug, page_slug):
    """View for public access to a specific page of a website via its shareable link"""
    # Handle 'None' string as a special case
    if public_slug == 'None':
        raise Http404("Website not found. Invalid public link.")
        
    website = get_object_or_404(Website, public_slug=public_slug)
    page = get_object_or_404(WebsitePage, website=website, slug=page_slug)
    
    # Ensure required fields exist in website content
    required_fields = [
        'meta_description', 'meta_keywords', 'site_name', 
        'hero_title', 'hero_subtitle', 'hero_button',
        'features_title', 'features_subtitle', 'features',
        'about_title', 'about_content', 'about_image', 'about_button',
        'cta_title', 'cta_subtitle', 'cta_main_button'
    ]
    
    # Copy description to meta_description if available
    if 'meta_description' not in website.content and 'description' in website.content:
        website.content['meta_description'] = website.content['description']
    
    # Ensure websiteName is copied to site_name if needed
    if 'site_name' not in website.content and 'websiteName' in website.content:
        website.content['site_name'] = website.content['websiteName']
    
    # Set default empty values for all required fields if missing
    for field in required_fields:
        if field not in website.content:
            if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                website.content[field] = {'url': '#', 'label': 'Learn More'}
            elif field == 'features':
                website.content[field] = [
                    {
                        'icon': 'palette',
                        'title': 'Beautiful Design',
                        'description': 'Modern and elegant designs that capture attention and create memorable experiences.'
                    },
                    {
                        'icon': 'mobile-alt',
                        'title': 'Responsive Layout',
                        'description': 'Our websites look amazing on all devices, from desktops to smartphones.'
                    },
                    {
                        'icon': 'bolt',
                        'title': 'Performance Optimized',
                        'description': 'Fast loading times and smooth performance for the best user experience.'
                    }
                ]
            elif field == 'about_image':
                website.content[field] = 'https://via.placeholder.com/600x400'
            else:
                website.content[field] = ""
    
    # Ensure required fields exist in page content
    if page.content is None:
        page.content = {}
        
    # Set default empty values for all required fields if missing in page content
    for field in required_fields:
        if field not in page.content:
            if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                page.content[field] = {'url': '#', 'label': 'Learn More'}
            elif field == 'features':
                page.content[field] = [
                    {
                        'icon': 'palette',
                        'title': 'Beautiful Design',
                        'description': 'Modern and elegant designs that capture attention and create memorable experiences.'
                    },
                    {
                        'icon': 'mobile-alt',
                        'title': 'Responsive Layout',
                        'description': 'Our websites look amazing on all devices, from desktops to smartphones.'
                    },
                    {
                        'icon': 'bolt',
                        'title': 'Performance Optimized',
                        'description': 'Fast loading times and smooth performance for the best user experience.'
                    }
                ]
            elif field == 'about_image':
                page.content[field] = 'https://via.placeholder.com/600x400'
            else:
                page.content[field] = ""
    
    # Use template path with forward slashes for Django template loader
    template_path = f"{website.template.template_path.strip('/')}/{page.template_file}"
    return render(request, template_path, {
        'website': website,
        'page': page,
        'content': page.content,
        'global_content': website.content,
        'is_public_view': True,
        'default_banners': [
            {
                'image': 'https://via.placeholder.com/1920x1080',
                'title': 'Welcome to Your Store',
                'description': 'Discover amazing products at great prices',
                'button_text': 'Shop Now',
                'button_url': '/shop'
            }
        ]
    })

@login_required
def delete_website(request, website_id):
    """Delete a website and all its associated data"""
    website = get_object_or_404(Website, id=website_id, user=request.user)
    
    if request.method == 'POST':
        try:
            # Get website name for the success message
            website_name = website.template.name if website.template else "Website"
            
            # Delete all associated files (logos, images, etc.)
            if website.content:
                # Delete logo files
                for logo_key in ['desktop_logo', 'mobile_logo', 'favicon']:
                    logo_path = website.content.get(logo_key)
                    if logo_path:
                        try:
                            full_path = os.path.join(settings.MEDIA_ROOT, logo_path.lstrip('/'))
                            if os.path.exists(full_path):
                                os.remove(full_path)
                        except Exception as e:
                            logger.error(f"Error deleting {logo_key} file: {str(e)}")
            
            # Delete the website (this will cascade delete associated records)
            # - WebsitePage (CASCADE)
            # - WebsiteCategory (CASCADE)
            # - WebsiteProduct (CASCADE)
            # - CustomDomain (CASCADE)
            website.delete()
            
            messages.success(request, f'"{website_name}" and all associated data have been deleted successfully!')
        except Exception as e:
            logger.error(f"Error deleting website {website_id}: {str(e)}")
            messages.error(request, f'An error occurred while deleting the website. Please try again or contact support.')
        
        return redirect('website_dashboard')
    
    # If not a POST request, redirect to dashboard
    return redirect('website_dashboard')

@login_required
def fix_all_slugs(request):
    """Admin utility to fix all missing public slugs"""
    if not request.user.is_staff:
        messages.error(request, "You don't have permission to access this page.")
        return redirect('website_dashboard')
    
    # Find all websites with None, 'None' or empty public_slug
    websites = Website.objects.filter(public_slug__isnull=True) | Website.objects.filter(public_slug='None') | Website.objects.filter(public_slug='')
    fixed_count = 0
    
    for website in websites:
        old_slug = website.public_slug
        website.save()  # This will generate a new slug
        fixed_count += 1
    
    messages.success(request, f'Fixed {fixed_count} websites with missing public slugs')
    return redirect('website_dashboard')

# Product Category and Product Management Views
@login_required
def product_category(request):
    """View for managing product categories"""
    # Get the current user's websites
    websites = Website.objects.filter(user=request.user)
    selected_website_id = request.GET.get('website_id') or request.session.get('selected_website_id')
    
    # Handle case when user has no websites
    if not websites.exists():
        messages.info(request, 'You need to create a website first before managing categories.')
        return redirect('website_dashboard')
    
    # If no website is selected or the selected website doesn't belong to the user, use the first one
    if not selected_website_id or not websites.filter(id=selected_website_id).exists():
        selected_website = websites.first()
        selected_website_id = selected_website.id
        request.session['selected_website_id'] = selected_website_id
    else:
        selected_website = websites.get(id=selected_website_id)
        request.session['selected_website_id'] = selected_website_id
    
    # Get categories for the selected website
    categories = WebsiteCategory.objects.filter(website=selected_website).order_by('order', 'name')
    
    if request.method == 'POST':
        category_name = request.POST.get('category_name')
        category_description = request.POST.get('category_description', '')
        edit_category_id = request.POST.get('edit_category_id')
        
        if edit_category_id:
            try:
                # Edit existing category
                category = WebsiteCategory.objects.get(id=edit_category_id, website=selected_website)
                category.name = category_name
                category.description = category_description
                category.save()
                messages.success(request, f'Category "{category_name}" updated successfully!')
            except WebsiteCategory.DoesNotExist:
                messages.error(request, 'Category not found')
        else:
            # Create new category
            if category_name:
                WebsiteCategory.objects.create(
                    website=selected_website,
                    name=category_name,
                    description=category_description
                )
                messages.success(request, f'Category "{category_name}" created successfully!')
            else:
                messages.error(request, 'Category name is required')
    
    return render(request, 'website/product_categories.html', {
        'categories': categories,
        'websites': websites,
        'selected_website': selected_website
    })

@login_required
def delete_category(request, category_id):
    """View for deleting a product category"""
    # Get the selected website from session
    selected_website_id = request.session.get('selected_website_id')
    
    if not selected_website_id:
        messages.error(request, 'No website selected')
        return redirect('website_product_category')
    
    try:
        # Ensure the category belongs to a website owned by the user
        category = WebsiteCategory.objects.get(
            id=category_id, 
            website__id=selected_website_id,
            website__user=request.user
        )
        
        category_name = category.name
        
        # Check if products exist with this category
        products_count = WebsiteProduct.objects.filter(category=category).count()
        if products_count > 0:
            messages.error(request, f'Cannot delete category "{category_name}" because it has {products_count} products assigned to it.')
        else:
            category.delete()
            messages.success(request, f'Category "{category_name}" deleted successfully!')
    except WebsiteCategory.DoesNotExist:
        messages.error(request, 'Category not found')
    
    return redirect('website_product_category')

@login_required
def products(request):
    """View for listing all products"""
    # Get the selected website from session
    selected_website_id = request.session.get('selected_website_id')
    
    # Get the current user's websites
    websites = Website.objects.filter(user=request.user)
    
    # Handle case when user has no websites
    if not websites.exists():
        messages.info(request, 'You need to create a website first before managing products.')
        return redirect('website_dashboard')
    
    # If no website is selected or the selected website doesn't belong to the user, use the first one
    if not selected_website_id or not websites.filter(id=selected_website_id).exists():
        selected_website = websites.first()
        selected_website_id = selected_website.id
        request.session['selected_website_id'] = selected_website_id
    else:
        selected_website = websites.get(id=selected_website_id)
        request.session['selected_website_id'] = selected_website_id
    
    # Get products and categories for the selected website
    products = WebsiteProduct.objects.filter(website=selected_website).order_by('-created_at')
    categories = WebsiteCategory.objects.filter(website=selected_website).order_by('name')
    
    return render(request, 'website/products.html', {
        'products': products,
        'categories': categories,
        'websites': websites,
        'selected_website': selected_website
    })

@login_required
def product_create(request):
    """View for creating a new product"""
    # Get the selected website from session
    selected_website_id = request.session.get('selected_website_id')
    
    # Ensure a website is selected
    if not selected_website_id:
        messages.error(request, 'Please select a website first')
        return redirect('website_products')
    
    # Get the website and ensure it belongs to the user
    try:
        selected_website = Website.objects.get(id=selected_website_id, user=request.user)
    except Website.DoesNotExist:
        messages.error(request, 'Website not found')
        return redirect('website_dashboard')
    
    # Get categories for the selected website
    categories = WebsiteCategory.objects.filter(website=selected_website).order_by('name')
    
    if request.method == 'POST':
        try:
            # Get form data
            product_title = request.POST.get('title')
            product_description = request.POST.get('description')
            product_price = request.POST.get('price')
            category_id = request.POST.get('category')
            hsn_code = request.POST.get('hsn_code')
            gst_percentage = request.POST.get('gst_percentage')
            youtube_link = request.POST.get('youtube_link', '')
            product_active = 'is_active' in request.POST
            
            # Get image files
            product_image1 = request.FILES.get('image1')
            product_image2 = request.FILES.get('image2', None)
            product_image3 = request.FILES.get('image3', None)
            product_image4 = request.FILES.get('image4', None)
            
            # Get variant data if available
            variant_data = []
            if request.POST.get('variants'):
                try:
                    variant_data = json.loads(request.POST.get('variants'))
                except json.JSONDecodeError:
                    messages.error(request, 'Invalid variant data format')
                    return render(request, 'website/product_form.html', {
                        'categories': categories,
                        'selected_website': selected_website
                    })
            
            # Get specifications data if available
            specifications_data = {}
            if request.POST.get('specifications'):
                try:
                    specifications_data = json.loads(request.POST.get('specifications'))
                except json.JSONDecodeError:
                    messages.error(request, 'Invalid specifications data format')
                    return render(request, 'website/product_form.html', {
                        'categories': categories,
                        'selected_website': selected_website
                    })
            
            # Get category if specified
            category = None
            if category_id:
                try:
                    category = WebsiteCategory.objects.get(id=category_id, website=selected_website)
                except WebsiteCategory.DoesNotExist:
                    messages.warning(request, f'Category not found, product will be created without a category')
            
            # Create product
            product = WebsiteProduct.objects.create(
                website=selected_website,
                category=category,
                title=product_title,
                description=product_description,
                price=product_price,
                image1=product_image1,
                image2=product_image2,
                image3=product_image3,
                image4=product_image4,
                variants=variant_data,
                specifications=specifications_data,
                video_link=youtube_link,
                hsn_code=hsn_code,
                gst_percentage=gst_percentage,
                is_active=product_active
            )
            
            messages.success(request, f'Product "{product_title}" created successfully!')
            return redirect('website_products')
            
        except Exception as e:
            messages.error(request, f'Error creating product: {str(e)}')
    
    return render(request, 'website/product_form.html', {
        'categories': categories,
        'selected_website': selected_website
    })

@login_required
def product_edit(request, product_id):
    """View for editing an existing product"""
    # Get the selected website from session
    selected_website_id = request.session.get('selected_website_id')
    
    # Ensure a website is selected
    if not selected_website_id:
        messages.error(request, 'Please select a website first')
        return redirect('website_products')
    
    try:
        # Get the product and ensure it belongs to the user's website
        product = WebsiteProduct.objects.get(
            product_id=product_id,
            website__id=selected_website_id,
            website__user=request.user
        )
        
        selected_website = product.website
        categories = WebsiteCategory.objects.filter(website=selected_website).order_by('name')
        
        if request.method == 'POST':
            try:
                # Get form data
                product.title = request.POST.get('title')
                product.description = request.POST.get('description')
                product.price = request.POST.get('price')
                category_id = request.POST.get('category')
                product.hsn_code = request.POST.get('hsn_code')
                product.gst_percentage = request.POST.get('gst_percentage')
                product.video_link = request.POST.get('youtube_link', '')
                product.is_active = 'is_active' in request.POST
                
                # Update category if specified
                if category_id:
                    try:
                        product.category = WebsiteCategory.objects.get(id=category_id, website=selected_website)
                    except WebsiteCategory.DoesNotExist:
                        messages.warning(request, f'Category not found, product will be saved without a category')
                        product.category = None
                else:
                    product.category = None
                
                # Update image files if new ones are uploaded
                if 'image1' in request.FILES:
                    product.image1 = request.FILES['image1']
                if 'image2' in request.FILES:
                    product.image2 = request.FILES['image2']
                if 'image3' in request.FILES:
                    product.image3 = request.FILES['image3']
                if 'image4' in request.FILES:
                    product.image4 = request.FILES['image4']
                
                # Update variant data if available
                if request.POST.get('variants'):
                    try:
                        product.variants = json.loads(request.POST.get('variants'))
                    except json.JSONDecodeError:
                        messages.error(request, 'Invalid variant data format')
                        return render(request, 'website/product_form.html', {
                            'product': product, 
                            'categories': categories,
                            'selected_website': selected_website
                        })
                
                # Update specifications data if available
                if request.POST.get('specifications'):
                    try:
                        product.specifications = json.loads(request.POST.get('specifications'))
                    except json.JSONDecodeError:
                        messages.error(request, 'Invalid specifications data format')
                        return render(request, 'website/product_form.html', {
                            'product': product, 
                            'categories': categories,
                            'selected_website': selected_website
                        })
                
                product.save()
                messages.success(request, f'Product "{product.title}" updated successfully!')
                return redirect('website_products')
                
            except Exception as e:
                messages.error(request, f'Error updating product: {str(e)}')
        
        # Prepare variant data for the template
        product.variant_list = product.variants
        
        return render(request, 'website/product_form.html', {
            'product': product,
            'categories': categories,
            'selected_website': selected_website
        })
        
    except WebsiteProduct.DoesNotExist:
        messages.error(request, 'Product not found')
        return redirect('website_products')

@login_required
def product_delete(request, product_id):
    """View for deleting a product"""
    # Get the selected website from session
    selected_website_id = request.session.get('selected_website_id')
    
    try:
        # Ensure the product belongs to a website owned by the user
        product = WebsiteProduct.objects.get(
            product_id=product_id,
            website__id=selected_website_id,
            website__user=request.user
        )
        
        product_title = product.title
        product.delete()
        messages.success(request, f'Product "{product_title}" deleted successfully!')
    except WebsiteProduct.DoesNotExist:
        messages.error(request, 'Product not found')
    
    return redirect('website_products')

@login_required
def product_detail(request, product_id):
    """View for viewing product details"""
    # Get the selected website from session
    selected_website_id = request.session.get('selected_website_id')
    
    try:
        # Ensure the product belongs to a website owned by the user
        product = WebsiteProduct.objects.get(
            product_id=product_id,
            website__id=selected_website_id,
            website__user=request.user
        )
        
        selected_website = product.website
        
        # Process variant data for template
        if product.variants and isinstance(product.variants, str):
            product.variant_list = json.loads(product.variants)
        else:
            product.variant_list = product.variants or []
            
        # Convert old variant format to new if needed
        if product.variant_list and len(product.variant_list) > 0 and 'name' in product.variant_list[0] and 'value' in product.variant_list[0]:
            # Old format, convert to type-value structure
            variant_types = {}
            for variant in product.variant_list:
                if variant['name'] not in variant_types:
                    variant_types[variant['name']] = {
                        'name': variant['name'],
                        'values': []
                    }
                
                variant_types[variant['name']]['values'].append({
                    'value': variant['value'],
                    'price': variant['price']
                })
            
            product.variant_list = list(variant_types.values())
        
        return render(request, 'website/product_detail.html', {
            'product': product,
            'selected_website': selected_website
        })
        
    except WebsiteProduct.DoesNotExist:
        messages.error(request, 'Product not found')
        return redirect('website_products')

def privacy_policy_page(request, public_slug):
    """View for the privacy policy page"""
    # Handle 'None' string as a special case
    if public_slug == 'None':
        raise Http404("Website not found. Invalid public link.")
        
    website = get_object_or_404(Website, public_slug=public_slug)
    
    # Use template path with forward slashes for Django template loader
    template_path = f"{website.template.template_path.strip('/')}/privacy-policy.html"
    
    return render(request, template_path, {
        'website': website,
        'global_content': website.content,
        'is_public_view': True
    })

def terms_conditions_page(request, public_slug):
    """View for the terms and conditions page"""
    # Handle 'None' string as a special case
    if public_slug == 'None':
        raise Http404("Website not found. Invalid public link.")
        
    website = get_object_or_404(Website, public_slug=public_slug)
    
    # Use template path with forward slashes for Django template loader
    template_path = f"{website.template.template_path.strip('/')}/terms-conditions.html"
    
    return render(request, template_path, {
        'website': website,
        'global_content': website.content,
        'is_public_view': True
    })

def refund_policy_page(request, public_slug):
    """View for the refund policy page"""
    # Handle 'None' string as a special case
    if public_slug == 'None':
        raise Http404("Website not found. Invalid public link.")
        
    website = get_object_or_404(Website, public_slug=public_slug)
    
    # Use template path with forward slashes for Django template loader
    template_path = f"{website.template.template_path.strip('/')}/refund-policy.html"
    
    return render(request, template_path, {
        'website': website,
        'global_content': website.content,
        'is_public_view': True
    })

@login_required
def view_enhanced_homepage(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    
    # Ensure website content has required fields initialized
    if website.content is None:
        website.content = {}
    
    # Initialize site_name from websiteName if it doesn't exist
    if 'site_name' not in website.content and 'websiteName' in website.content:
        website.content['site_name'] = website.content['websiteName']
    elif 'site_name' not in website.content:
        website.content['site_name'] = website.content.get('meta_title', '').split(' - ')[0]
    
    # Initialize favicon if it doesn't exist
    if 'favicon' not in website.content:
        website.content['favicon'] = ''
        
    # Get homepage
    homepage = website.pages.filter(is_homepage=True).first()
    
    # Save the updated content
    website.save()
    
    context = {
        'website': website,
        'default_banners': [
            {
                'image': 'https://via.placeholder.com/1920x1080',
                'title': 'Welcome to Our Store',
                'description': 'Discover quality products at exceptional prices',
                'button_text': 'Shop Now',
                'button_url': '/shop',
                'alt_text': 'Featured product collection banner'
            },
            {
                'image': 'https://via.placeholder.com/1920x1080',
                'title': 'New Arrivals',
                'description': 'Check out our latest collection',
                'button_text': 'Explore Now',
                'button_url': '/new-arrivals',
                'alt_text': 'New arrivals banner'
            },
            {
                'image': 'https://via.placeholder.com/1920x1080',
                'title': 'Summer Sale',
                'description': 'Up to 50% off on selected items',
                'button_text': 'Shop Sale',
                'button_url': '/sale',
                'alt_text': 'Summer sale promotion banner'
            }
        ],
        'now': timezone.now(),
        'request': request,
        'is_public_view': False
    }
    
    if homepage:
        context.update({
            'page': homepage,
            'content': homepage.content,
            'global_content': website.content,
        })
    else:
        context.update({
            'content': website.content,
        })
    
    return render(request, "website/template1/enhanced_home.html", context)

@login_required
def apply_enhanced_template(request, website_id):
    website = get_object_or_404(Website, id=website_id, user=request.user)
    
    try:
        # Apply the enhanced content structure to the website
        if 'meta_title' not in website.content:
            website.content['meta_title'] = website.content.get('site_name', '') + ' - Professional Website'
        
        if 'meta_description' not in website.content:
            website.content['meta_description'] = 'Welcome to ' + website.content.get('site_name', 'our website') + '. ' + website.content.get('hero_subtitle', '')
        
        # Add SEO-friendly content structure 
        website.content['seo_enabled'] = True
        website.content['structured_data'] = {
            'organization': {
                'name': website.content.get('site_name', ''),
                'url': request.build_absolute_uri(website.get_public_url()),
                'logo': website.content.get('logo_url', '')
            }
        }
        
        # Save the changes
        website.save()
        
        messages.success(request, 'Enhanced SEO template has been applied successfully!')
    except Exception as e:
        messages.error(request, f'Error applying template: {str(e)}')
    
    return redirect('edit_website', website_id=website.id)

@login_required
def seo_management(request, website_id):
    """View for managing website SEO settings"""
    website = get_object_or_404(Website, id=website_id, user=request.user)
    
    if request.method == 'POST':
        try:
            # Parse JSON data from request body, with fallback to form data for compatibility
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                # Try to get data from POST parameters if JSON parsing fails
                data = {
                    'meta_title': request.POST.get('meta_title', ''),
                    'meta_description': request.POST.get('meta_description', ''),
                    'meta_keywords': request.POST.get('meta_keywords', ''),
                    'organization_name': request.POST.get('organization_name', ''),
                    'organization_url': request.POST.get('organization_url', ''),
                    'organization_logo': request.POST.get('organization_logo', ''),
                    'organization_description': request.POST.get('organization_description', ''),
                    'og_title': request.POST.get('og_title', ''),
                    'og_description': request.POST.get('og_description', ''),
                    'og_image': request.POST.get('og_image', ''),
                    'facebook_url': request.POST.get('facebook_url', ''),
                    'twitter_url': request.POST.get('twitter_url', ''),
                    'instagram_url': request.POST.get('instagram_url', ''),
                    'linkedin_url': request.POST.get('linkedin_url', ''),
                    'youtube_url': request.POST.get('youtube_url', ''),
                }
            
            # Update SEO content using the new method
            website.update_seo_content(data)
            
            return JsonResponse({
                'status': 'success', 
                'message': 'SEO settings updated successfully!',
                'content': website.content  # Return updated content for verification
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error', 
                'message': str(e),
                'details': 'Error updating SEO settings'
            }, status=400)
    
    # Get SEO data from the website content
    seo_data = website.content.get('seo', {})
    
    # Prepare data for the template
    template_data = {
        'meta_title': seo_data.get('meta_title', ''),
        'meta_description': seo_data.get('meta_description', ''),
        'meta_keywords': seo_data.get('meta_keywords', ''),
        'og_title': seo_data.get('og_title', ''),
        'og_description': seo_data.get('og_description', ''),
        'og_image': seo_data.get('og_image', ''),
    }
    
    # Get structured data if available
    structured_data = seo_data.get('structured_data', {})
    organization = structured_data.get('organization', {})
    
    # Get social links if available
    social_links = seo_data.get('social_links', {})
    
    return render(request, 'website/seo_management.html', {
        'website': website,
        'seo_data': template_data,
        'organization': organization,
        'social_links': social_links,
        'public_url': request.build_absolute_uri(website.get_public_url())
    })

@login_required
def debug_fix_templates(request):
    """Debug utility to fix websites with missing or broken template references"""
    if not request.user.is_superuser:
        messages.error(request, 'Only superusers can access this utility.')
        return redirect('website_dashboard')
    
    # Get all websites for the current user
    websites = Website.objects.filter(user=request.user)
    fixed_count = 0
    
    for website in websites:
        fixed = False
        
        # Fix missing template
        if website.template is None:
            # Try to assign the first active template
            templates = WebsiteTemplate.objects.filter(is_active=True)
            if templates.exists():
                website.template = templates.first()
                fixed = True
        
        # Fix missing public slug
        if not website.public_slug or website.public_slug == 'None':
            website.save()  # This will generate a new slug
            fixed = True
            
        # Check if website has a homepage
        homepage = website.pages.filter(is_homepage=True).first()
        if not homepage:
            # Create a default homepage
            WebsitePage.objects.create(
                website=website,
                title='Home',
                slug='home',
                template_file='home.html',
                is_homepage=True,
                order=0,
                content=website.content
            )
            fixed = True
        
        if fixed:
            website.save()
            fixed_count += 1
    
    messages.success(request, f'Fixed {fixed_count} websites with template or homepage issues.')
    return redirect('website_dashboard')

def category_detail(request, public_slug, category_slug):
    """View for displaying category details and its products"""
    # Handle 'None' string as a special case
    if public_slug == 'None':
        raise Http404("Website not found. Invalid public link.")
        
    website = get_object_or_404(Website, public_slug=public_slug)
    category = get_object_or_404(WebsiteCategory, website=website, slug=category_slug)
    
    # Get products for this category
    products = WebsiteProduct.objects.filter(
        website=website,
        category=category,
        is_active=True
    ).order_by('-created_at')
    
    # Use template path with forward slashes for Django template loader
    template_path = f"{website.template.template_path.strip('/')}/category_detail.html"
    
    return render(request, template_path, {
        'website': website,
        'category': category,
        'products': products,
        'global_content': website.content,
        'is_public_view': True
    })

def shop_redirect(request, public_slug):
    """View for redirecting shop link to the first active category"""
    # Handle 'None' string as a special case
    if public_slug == 'None':
        raise Http404("Website not found. Invalid public link.")
        
    website = get_object_or_404(Website, public_slug=public_slug)
    
    # Get the first active category
    first_category = WebsiteCategory.objects.filter(
        website=website,
        is_active=True
    ).order_by('order', 'name').first()
    
    if first_category:
        # Redirect to the category detail page
        return redirect('category_detail', public_slug=public_slug, category_slug=first_category.slug)
    else:
        # If no categories exist, show a message and redirect to home
        messages.info(request, 'No categories available yet.')
        return redirect('public_website', public_slug=public_slug)
