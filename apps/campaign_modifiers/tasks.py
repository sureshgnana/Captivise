import logging

from celery.task import task


#@task(name='campaign_modifiers.run_scripts')
def run_scripts():
    from adwords.adapter import Adapter
    from accounts.models import User

    from .modifiers.hcpa import HighCostPerAcquisitionModifier
    from .modifiers.lcpa import LowCostPerAcquisitionModifier
    from .modifiers.lctr import LowClickThroughRate
    from .modifiers.lp import LowPosition
    from .modifiers.pause_empty_ad_groups import PauseEmptyAdGroups
    from .modifiers.tcpa import TargetCostPerAcquisition
    from .modifiers.tcpa_margin import TargetCostPerAcquisitionMargin
    from .modifiers.zc import ZeroClicks
    from .modifiers.zc_margin import ZeroClicksMargin
    from .utils import ModifierProcess

    for user in User.objects.all():
        if not user.has_payment_details:
            continue  # Skip unpaid users.

        api_adapter = Adapter(user)

        for campaign in user.campaigns.filter(is_managed=True):
            if campaign.conversion_type == campaign.CONVERSION_TYPE_CPA:
                modifiers_in_order = (
                    PauseEmptyAdGroups(),
                    LowPosition(),
                    ZeroClicks(),
                    LowClickThroughRate(),
                    TargetCostPerAcquisition(),
                    LowCostPerAcquisitionModifier(),
                    HighCostPerAcquisitionModifier(),
                )
            elif campaign.conversion_type == campaign.CONVERSION_TYPE_MARGIN:
                modifiers_in_order = (
                    PauseEmptyAdGroups(),
                    LowPosition(),
                    ZeroClicksMargin(),
                    LowClickThroughRate(),
                    TargetCostPerAcquisitionMargin(),
                )
            else:
                logger = logging.getLogger('celery')
                message = (
                    'Error while running modifiers on campaign id'
                    ' {campaign_id} for user id {user_id} - unknown'
                    ' `conversion_type`'
                ).format(campaign_id=campaign.id, user_id=user.id)
                logger.error(message)

                continue

            try:
                ModifierProcess().run(
                    modifiers_in_order,
                    api_adapter,
                    campaign.adwords_campaign_id,
                    is_dry_run=user.is_adwords_dry_run,
                    target_cpa=campaign.target_cpa,
                    max_cpc_limit=campaign.max_cpc_limit,
                    cycle_period=campaign.cycle_period_days,
                )
            except:  # Don't let one user bring down everyone's scripts.
                logger = logging.getLogger('celery')
                message = (
                    'Error while running modifiers on campaign id'
                    ' {campaign_id} for user id {user_id}'
                ).format(campaign_id=campaign.id, user_id=user.id)
                logger.exception(message)
