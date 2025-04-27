from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from invoicing.models import Recipent, Invoice
# Create your views here.

class IndexView(TemplateView):
    template_name = 'onematrix/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = '1Matrix - Professional Services Portal'
        return context

def is_mobile(request):
    """Detect if the request is coming from a mobile device"""
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    mobile_keywords = ['mobile', 'android', 'iphone' , 'windows phone']
    return any(keyword in user_agent for keyword in mobile_keywords)

class HomeView(TemplateView):
    def get_template_names(self):
        if is_mobile(self.request):
            return ['onematrix/mobile.html']
        return ['onematrix/home.html']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

class ContactUsView(TemplateView):
    template_name = 'onematrix/contact-us.html'
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

class AboutUsView(TemplateView):
    template_name = 'onematrix/about-us.html'
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

class PrivacyPolicyView(TemplateView):
    template_name = 'onematrix/privacy-policy.html'
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

class TermsAndConditionsView(TemplateView):
    template_name = 'onematrix/terms-and-conditions.html'
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context

class CancellationView(TemplateView):
    template_name = 'onematrix/cancellation.html'
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context




class InvoiceReportsView(TemplateView):
    template_name = 'onematrix/invoice-reports.html'
    
    def dispatch(self, request, *args, **kwargs):
        recipient_id = kwargs.get('recipient_id')
        session_recipient_id = request.session.get('recipent_id')
        
        # Check if user is authenticated and accessing their own reports
        if not session_recipient_id or session_recipient_id != recipient_id:
            return redirect('home')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        recipient_id = kwargs.get('recipient_id')
        recipient = Recipent.objects.get(recipent_id=recipient_id)
        context['recipient'] = recipient
        # Get all invoices from companies the recipient has access to
        invoices = Invoice.objects.filter(company__in=recipient.companies.all())
        companies = recipient.companies.all()
        
        context['invoices'] = invoices
        context['companies'] = companies
        return context

