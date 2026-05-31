from django.shortcuts import render
from django.db.models import Sum, Avg
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from activities.models import Activity
from .forms import SeasonPassForm, SeasonPass
import logging
from django.http import HttpResponseRedirect
from osm.models import SkiArea, SkiAreaNetwork
from django.db.models.functions import Round
from core.premium import premium_required

logger = logging.getLogger(__name__)

@login_required
def cost_detail(request, season=None):
    activities = Activity.objects.filter(user=request.user)
    context = {
        'activities': activities,
        'sum_cost': activities.aggregate(Sum('cost'))['cost__sum'], 
        'sum_value': activities.aggregate(Sum('value'))['value__sum'],
        'avg_cost': activities.aggregate(Avg('cost'))['cost__avg'],
    }

    return render(request, "core/cost/cost_detail.html", context)


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
        'count': activities.count(),
        'sum_cost': activities.aggregate(Sum('cost'))['cost__sum'], 
        'sum_value': activities.aggregate(Sum('value'))['value__sum'],
        'avg_cost': activities.aggregate(Avg('cost'))['cost__avg'],
    }

    return render(request, "cost/cost_detail_network.html", context)


@login_required
@premium_required
def cost_home(request):

    logger.debug(request)

    if request.method == 'POST':
        form = SeasonPassForm(request.POST)
        logger.debug(form)
        if form.is_valid():
            pass_form = form.save(commit=False)
            pass_form.user = request.user
            pass_form.save()
            return redirect('cost_home')
        else:
            logger.debug(form.errors)
            message = "There were errors in your form. Please correct them."

    passes = SeasonPass.objects.filter(user=request.user).order_by('-valid_until')

    for p in passes:
        logger.debug(p.count_valid_activities())
        logger.debug(p.get_valid_activities())

    context = {
        'passes': passes,
        'networks_dropdown': SkiAreaNetwork.objects.all().order_by('name'),
        'message': message if 'message' in locals() else None,
        'form': SeasonPassForm(),
    }
    return render(request, "cost/cost_home.html", context)


@login_required
@premium_required
def season_pass_detail(request, pass_id):
    season_pass = get_object_or_404(SeasonPass, id=pass_id, user=request.user)
    if season_pass.skiarea_network:
        activities = Activity.objects.filter(
                    user=request.user,
                    ski_area__in=season_pass.skiarea_network.members.values_list('member', flat=True),  
                    start_time__gte=season_pass.valid_from,
                    start_time__lte=season_pass.valid_until
                    ).order_by('-timestamp')
    else:
        activities = Activity.objects.filter(user=request.user,
                                            ski_area=season_pass.skiarea, 
                                            start_time__gte=season_pass.valid_from, 
                                            start_time__lte=season_pass.valid_until).order_by('-timestamp')

    activities = activities.annotate(
        total_distance_km=Round(Sum('total_distance') / 1000, 2)
    )

    # Summer activities attributed to this pass (manually tracked).
    summer_activities = (
        season_pass.get_summer_activities()
        .select_related('activity_type', 'ski_area')
        .order_by('-date')
    )

    context = {
        'season_pass': season_pass,
        'activities': activities,
        # Winter cost/day already deducts total summer value (see SeasonPass.cost_per_day).
        'cost_per_day': season_pass.cost_per_day,
        'sum_cost': activities.aggregate(Sum('cost'))['cost__sum'],
        'sum_value': activities.aggregate(Sum('value'))['value__sum'],
        'summer_activities': summer_activities,
        'summer_count': summer_activities.count(),
        'total_summer_value': season_pass.total_summer_value,
        'summer_avg_value': season_pass.summer_avg_value,
    }

    return render (request, "cost/season_pass_detail.html", context)

@login_required
@premium_required
def delete_season_pass(request, pass_id):
    season_pass = get_object_or_404(SeasonPass, id=pass_id, user=request.user)
    season_pass.delete()
    return redirect('home')