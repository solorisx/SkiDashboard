from django.core.management.base import BaseCommand
from core.debug import test_strava, print_activities, test_strava_activity


class Command(BaseCommand):
    help = "Tests the Strava interface"

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            nargs="?",
            default=None,
            help="Specify 'test' to run test_strava or 'print' to run print_activities",
        )

    def handle(self, *args, **options):

        if options["action"] == "print":
            print_activities()
        elif options["action"]:
            test_strava_activity(options["action"])
        else:
            test_strava()
