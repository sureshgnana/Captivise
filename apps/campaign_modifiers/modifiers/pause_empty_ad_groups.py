from ..utils import ModifierBase


class PauseEmptyAdGroups(ModifierBase):
    name = 'Pause empty ad groups'

    def run(self, api_adapter, adwords_campaign_id, log=None, **kwargs):
        keywords = list(api_adapter.get_keywords_for_campaign(adwords_campaign_id))

        ad_group_ids = set((keyword['ad_group_id'] for keyword in keywords))
        ad_groups_with_enabled_keywords = set()
        for keyword in keywords:
            if keyword['status'] == 'enabled':
                ad_groups_with_enabled_keywords.add(keyword['ad_group_id'])

        ad_groups_without_enabled_keywords = ad_group_ids.difference(
            ad_groups_with_enabled_keywords)

        if ad_groups_without_enabled_keywords:
            api_adapter.set_ad_groups_paused(ad_groups_without_enabled_keywords)

        # TODO:  No logging for pausing entire ad groups, as we are
        # focused on logging keyword-centric events, and this seems
        # like simple housekeeping that doesn't actually effect the way
        # the ads are run.  Is this correct?
