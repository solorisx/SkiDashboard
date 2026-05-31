"""
Views for manually tracked summer (off-season) activities.

These deliberately operate on the :class:`SummerActivity` model only, keeping
them fully separate from the GPS/lift parsing pipeline and from every
ski-specific view (which query :class:`Activity`).
"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import SummerActivityForm
from ..models import SummerActivity, SummerActivityType

logger = logging.getLogger(__name__)


@login_required
def summer_activity_list(request):
    """List the user's summer activities with type/year filters and totals."""
    activities = (
        SummerActivity.objects
        .filter(user=request.user)
        .select_related('activity_type', 'ski_area', 'season_pass')
        .order_by('-date')
    )

    selected_type = request.GET.get('type') or None
    if selected_type:
        activities = activities.filter(activity_type__natural_key=selected_type)

    selected_year = request.GET.get('year') or None
    if selected_year:
        try:
            activities = activities.filter(date__year=int(selected_year))
        except (TypeError, ValueError):
            selected_year = None

    years = [
        d.year for d in
        SummerActivity.objects.filter(user=request.user).dates('date', 'year', order='DESC')
    ]
    totals = activities.aggregate(total_cost=Sum('cost'), total_value=Sum('value'))

    context = {
        'activities': activities,
        'types': SummerActivityType.for_user(request.user),
        'selected_type': selected_type,
        'years': years,
        'selected_year': selected_year,
        'count': activities.count(),
        'total_cost': totals['total_cost'],
        'total_value': totals['total_value'],
    }
    return render(request, 'activities/summer_activity_list.html', context)


@login_required
def summer_activity_create(request):
    if request.method == 'POST':
        form = SummerActivityForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Summer activity added.')
            return redirect('summer_activity_list')
    else:
        form = SummerActivityForm(user=request.user)
    return render(request, 'activities/summer_activity_form.html', {'form': form, 'mode': 'create'})


@login_required
def summer_activity_edit(request, pk):
    activity = get_object_or_404(SummerActivity, pk=pk, user=request.user)
    if request.method == 'POST':
        form = SummerActivityForm(request.POST, instance=activity, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Summer activity updated.')
            return redirect('summer_activity_list')
    else:
        form = SummerActivityForm(instance=activity, user=request.user)
    return render(
        request,
        'activities/summer_activity_form.html',
        {'form': form, 'mode': 'edit', 'activity': activity},
    )


@login_required
def summer_activity_delete(request, pk):
    activity = get_object_or_404(SummerActivity, pk=pk, user=request.user)
    if request.method == 'POST':
        activity.delete()
        messages.success(request, 'Summer activity deleted.')
        return redirect('summer_activity_list')
    return render(
        request,
        'activities/summer_activity_confirm_delete.html',
        {'activity': activity},
    )
