from django.shortcuts import render
from django.db.models import Sum, Avg
from django.contrib.auth.decorators import login_required
from activities.models import Activity


@login_required
def cost_detail(request, season=None):
    activities = Activity.objects.filter(user=request.user)
    context = {
        'activities': activities,
        'sum_cost': activities.aggregate(Sum('cost'))['cost__sum'], 
        'sum_value': activities.aggregate(Sum('value'))['value__sum'],
        'avg_cost': activities.aggregate(Avg('cost'))['cost__avg'],
    }

    return render(request, "cost/cost_detail.html", context)


@login_required
def cost_detail_network(request, season=None):
    activities = Activity.objects.filter(user=request.user)

    networks = activities.ski_area_main.values('network').annotate(
        total_cost=Sum('cost'),
        total_value=Sum('value'),
        avg_cost=Avg('cost'),
    ).order_by('-total_cost')

    context = {
        'activities': activities,
        'networks': networks,
        'sum_cost': activities.aggregate(Sum('cost'))['cost__sum'], 
        'sum_value': activities.aggregate(Sum('value'))['value__sum'],
        'avg_cost': activities.aggregate(Avg('cost'))['cost__avg'],
    }

    return render(request, "cost/cost_detail_network.html", context)