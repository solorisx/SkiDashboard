from django.shortcuts import render
from django.db.models import Sum, Avg
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from activities.models import Activity
from .forms import SeasonPassForm, SeasonPass
import logging
from django.http import HttpResponseRedirect

logger = logging.getLogger('core')

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


@login_required
def cost_home(request):

    logger.debug(request)

    if request.method == 'POST':
        form = SeasonPassForm(request.POST)
        logger.debug(form)
        if form.is_valid():
            pass_form = form.save(commit=False)
            pass_form.user = request.user
            pass_form.save()
            return(HttpResponseRedirect(''))
        else:
            logger.debug(form.errors)
            context = {
                'passes': SeasonPass.objects.filter(user=request.user),
                'form': form,
            }
            render(request, "cost_home.html", context)
    context = {
        'passes': SeasonPass.objects.filter(user=request.user),
        'form': SeasonPassForm(),
    }
    return render(request, "cost_home.html", context)


@login_required
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
    
    context = {
        'season_pass': season_pass,
        'activities': activities,
    }

    return render (request, "season_pass_detail.html", context)

@login_required
def delete_season_pass(request, pass_id):
    season_pass = get_object_or_404(SeasonPass, id=pass_id, user=request.user)
    season_pass.delete()
    return redirect('home')