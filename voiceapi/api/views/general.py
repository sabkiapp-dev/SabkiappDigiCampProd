# views/general.py
from django.http import HttpResponse
from django.shortcuts import render

def homepage(request):
    return HttpResponse("Welcome to the homepage!")
