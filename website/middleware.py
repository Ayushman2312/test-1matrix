from django.http import HttpResponseNotFound
from django.shortcuts import render
from .models import CustomDomain, DomainLog, Website, WebsitePage, WebsiteTemplate
import os
from django.contrib.auth.models import User
from django.utils.text import slugify
import uuid

class CustomDomainMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def _create_default_records(self, domain_name):
        """Create default Website, Template, and Homepage records for a new domain"""
        try:
            # Get or create a system user for default websites
            system_user, _ = User.objects.get_or_create(
                username='system',
                defaults={
                    'email': 'system@1matrix.in',
                    'is_staff': True,
                    'is_superuser': True
                }
            )

            # Get or create a default template
            default_template, _ = WebsiteTemplate.objects.get_or_create(
                name='Default Template',
                defaults={
                    'description': 'A clean and modern default template',
                    'template_path': 'website/template1',
                    'content_schema': {},
                    'is_active': True
                }
            )

            # Create a new website with default content
            website = Website.objects.create(
                user=system_user,
                template=default_template,
                content={
                    'site_name': domain_name,
                    'websiteName': domain_name,
                    'description': f'Welcome to {domain_name}',
                    'meta_description': f'Welcome to {domain_name} - Your trusted online destination',
                    'meta_keywords': f'{domain_name}, website, online',
                    'hero_title': f'Welcome to {domain_name}',
                    'hero_subtitle': 'Your trusted online destination',
                    'hero_button': {'url': '#', 'label': 'Learn More'},
                    'features_title': 'Our Features',
                    'features_subtitle': 'What makes us special',
                    'features': [
                        {
                            'icon': 'palette',
                            'title': 'Beautiful Design',
                            'description': 'Modern and elegant designs that capture attention.'
                        },
                        {
                            'icon': 'mobile-alt',
                            'title': 'Responsive Layout',
                            'description': 'Looks amazing on all devices.'
                        },
                        {
                            'icon': 'bolt',
                            'title': 'Performance Optimized',
                            'description': 'Fast loading times and smooth performance.'
                        }
                    ],
                    'about_title': 'About Us',
                    'about_content': f'Welcome to {domain_name}. We are committed to providing the best service.',
                    'about_image': 'https://via.placeholder.com/600x400',
                    'about_button': {'url': '#', 'label': 'Learn More'},
                    'cta_title': 'Get Started',
                    'cta_subtitle': 'Join us today',
                    'cta_main_button': {'url': '#', 'label': 'Get Started'}
                }
            )

            # Create a homepage
            WebsitePage.objects.create(
                website=website,
                title='Home',
                slug='home',
                template_file='home.html',
                is_homepage=True,
                order=0,
                content=website.content
            )

            # Create the custom domain record
            custom_domain = CustomDomain.objects.create(
                website=website,
                domain=domain_name,
                verification_status='verified',
                verification_code=str(uuid.uuid4()),
                ssl_status=False
            )

            return custom_domain

        except Exception as e:
            # Log the error
            DomainLog.objects.create(
                domain=domain_name,
                status_code=500,
                message=f'Error creating default records: {str(e)}'
            )
            return None

    def __call__(self, request):
        host = request.get_host().lower()
        
        # Skip middleware for admin, static URLs and app-specific paths
        if self._should_skip_middleware(request):
            return self.get_response(request)
        
        try:
            # Check if this is a custom domain request
            domain = CustomDomain.objects.get(
                domain=host, 
                verification_status='verified'
            )
            
            # Add website context to the request
            request.website = domain.website
            
            # Ensure required fields exist in website content
            required_fields = [
                'meta_description', 'meta_keywords', 'site_name', 
                'hero_title', 'hero_subtitle', 'hero_button',
                'features_title', 'features_subtitle', 'features',
                'about_title', 'about_content', 'about_image', 'about_button',
                'cta_title', 'cta_subtitle', 'cta_main_button'
            ]
            
            # Copy description to meta_description if available
            if 'meta_description' not in domain.website.content and 'description' in domain.website.content:
                domain.website.content['meta_description'] = domain.website.content['description']
            
            # Ensure websiteName is copied to site_name if needed
            if 'site_name' not in domain.website.content and 'websiteName' in domain.website.content:
                domain.website.content['site_name'] = domain.website.content['websiteName']
            
            # Set default empty values for all required fields if missing
            for field in required_fields:
                if field not in domain.website.content:
                    if field == 'hero_button' or field == 'about_button' or field == 'cta_main_button':
                        domain.website.content[field] = {'url': '#', 'label': 'Learn More'} 
                    elif field == 'features':
                        domain.website.content[field] = [
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
                        domain.website.content[field] = 'https://via.placeholder.com/600x400'
                    else:
                        domain.website.content[field] = ""
            
            # Get the page path from the URL
            path = request.path.strip('/')
            
            # Handle root path as homepage
            if not path:
                # Get homepage
                homepage = WebsitePage.objects.filter(
                    website=domain.website,
                    is_homepage=True
                ).first()
                
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
                    
                    # Render homepage
                    template_path = os.path.join(
                        domain.website.template.template_path.strip('/'),
                        homepage.template_file
                    )
                    return render(request, template_path, {
                        'website': domain.website,
                        'page': homepage,
                        'content': homepage.content,
                        'global_content': domain.website.content,
                        'seo_data': self._prepare_seo_data(domain.website, homepage)
                    })
                else:
                    # No specific homepage set, use default template home.html
                    template_path = os.path.join(
                        domain.website.template.template_path.strip('/'),
                        'home.html'
                    )
                    return render(request, template_path, {
                        'website': domain.website,
                        'content': domain.website.content,
                        'seo_data': self._prepare_seo_data(domain.website)
                    })
            else:
                # Try to find a matching page by slug
                try:
                    page = WebsitePage.objects.get(
                        website=domain.website,
                        slug=path
                    )
                    
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
                    
                    # Render the page using its template
                    template_path = os.path.join(
                        domain.website.template.template_path.strip('/'),
                        page.template_file
                    )
                    return render(request, template_path, {
                        'website': domain.website,
                        'page': page,
                        'content': page.content,
                        'global_content': domain.website.content,
                        'seo_data': self._prepare_seo_data(domain.website, page)
                    })
                except WebsitePage.DoesNotExist:
                    # Check if there's a template file matching the path
                    template_path = os.path.join(
                        domain.website.template.template_path.strip('/'),
                        f"{path}.html"
                    )
                    template_full_path = os.path.join('templates', template_path)
                    
                    if os.path.exists(template_full_path):
                        # Render the template with the global content
                        return render(request, template_path, {
                            'website': domain.website,
                            'content': domain.website.content,
                            'seo_data': self._prepare_seo_data(domain.website)
                        })
                    else:
                        # Return 404 for non-existent pages
                        DomainLog.objects.create(
                            domain=host, 
                            status_code=404,
                            message=f'Page not found: {path}'
                        )
                        return HttpResponseNotFound('Page not found')
            
        except CustomDomain.DoesNotExist:
            # Only create default records for non-local domains
            if not self._is_local_domain(host):
                # Try to create default records
                domain = self._create_default_records(host)
                if domain:
                    # Add website context to the request
                    request.website = domain.website
                    
                    # Render the default homepage
                    template_path = os.path.join(
                        domain.website.template.template_path.strip('/'),
                        'home.html'
                    )
                    return render(request, template_path, {
                        'website': domain.website,
                        'content': domain.website.content,
                        'seo_data': self._prepare_seo_data(domain.website)
                    })
                else:
                    # Log and return 404 if creation failed
                    DomainLog.objects.create(
                        domain=host, 
                        status_code=404,
                        message='Failed to create default website'
                    )
                    return HttpResponseNotFound('Website not found')
        
        response = self.get_response(request)
        return response
    
    def _should_skip_middleware(self, request):
        """Check if the request should skip custom domain processing"""
        path = request.path_info.lstrip('/')
        for prefix in ['admin/', 'alavi07/', 'static/', 'media/', 'api/']:
            if path.startswith(prefix):
                return True
                
        # Skip for specific apps
        for app in ['masteradmin/', 'agents/', 'customersupport/', 'user/', 'employee/', 'fee_calculator/', 
                    'listing_creater/', 'product_card/', 'invoicing/', 'hr_management/', 'blackbox/', 'trends/', 'data_miner/']:
            if path.startswith(app):
                return True
                
        return False
    
    def _is_local_domain(self, host):
        """Check if this is a local/development domain"""
        local_domains = [
            'localhost:8000',
            '127.0.0.1:8000',
            '[::1]',
            '.test',
            '.local',
            '.devtunnels.ms',
        ]
        
        for domain in local_domains:
            if host.endswith(domain) or host == domain:
                return True
        
        return False

    def _is_main_domain(self, host):
        main_domains = ['1matrix.in', 'www.1matrix.in', '89.116.20.128']
        return host in main_domains or host.startswith('localhost') or host.startswith('127.0.0.1')
        
    def _prepare_seo_data(self, website, page=None):
        """Prepare SEO data for templates"""
        
        # Get website content or initialize empty dict
        website_content = website.content or {}
        
        # Get page content if available
        page_content = page.content if page else {}
        
        # Prepare SEO data dictionary
        seo_data = {
            # Meta title: Page title if available, otherwise website title
            'meta_title': page_content.get('meta_title', 
                          website_content.get('meta_title', 
                          page_content.get('title', 
                          website_content.get('site_name', 'Website')))),
                          
            # Meta description: Page description if available, otherwise website description
            'meta_description': page_content.get('meta_description', 
                               website_content.get('meta_description', 
                               website_content.get('hero_subtitle', ''))),
                               
            # Meta keywords
            'meta_keywords': page_content.get('meta_keywords', 
                            website_content.get('meta_keywords', '')),
                            
            # Open Graph data
            'og_title': page_content.get('og_title', 
                       website_content.get('og_title', 
                       page_content.get('meta_title', 
                       website_content.get('meta_title', '')))),
                       
            'og_description': page_content.get('og_description', 
                            website_content.get('og_description', 
                            page_content.get('meta_description', 
                            website_content.get('meta_description', '')))),
                            
            'og_image': page_content.get('og_image', 
                      website_content.get('og_image', '')),
                      
            # Structured data
            'structured_data': website_content.get('structured_data', {}),
            
            # Social links
            'social_links': website_content.get('social_links', {})
        }
        
        return seo_data