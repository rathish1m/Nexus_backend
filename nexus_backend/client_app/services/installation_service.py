from site_survey.models import SiteSurvey


class InstallationService:
    @staticmethod
    def schedule_installation(order):
        SiteSurvey.objects.get_or_create(
            order=order,
            defaults={
                "surveyor": None,
                "status": "pending",
                "notes": "Site survey requested – awaiting scheduling",
            },
        )
