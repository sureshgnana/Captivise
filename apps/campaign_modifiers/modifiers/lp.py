import math

from ..utils import ModifierBase


class LowPosition(ModifierBase):
    name = 'Low position'

    def run(self, api_adapter, adwords_campaign_id, log=None, **kwargs):
        date_range = self.get_date_range_from_now(90)
        keywords = list(api_adapter.get_keywords_for_campaign(
            adwords_campaign_id, enabled_only=True, date_range=date_range))
        campaign = api_adapter.get_campaigns(
            campaigns_to_get=[adwords_campaign_id], get_budgets=False)[0]

        campaign_conversions = campaign['click_assisted_conversions']
        avg_average_position = (
            sum((keyword['average_position'] for keyword in keywords)) / len(keywords)
        )

        # `required_conversions` is the minimum conversions a keyword
        # must have if its position is over `maximum_position`.
        required_conversions = math.ceil(campaign_conversions / 200)
        maximum_position = max(
            avg_average_position + 7,
            avg_average_position * 3,
        )

        for keyword in keywords:
            keyword_id = keyword['id']
            max_cpc = keyword['max_cpc']

            modifier_data = {
                'campaign_conversions': campaign_conversions,
                'maximum_position': maximum_position,
                'avg_average_position': avg_average_position,
                'required_conversions': required_conversions,
                'max_cpc': max_cpc,
                'average_position': keyword['average_position'],
                'click_assisted_conversions': keyword['click_assisted_conversions'],
            }

            should_skip_keyword = self.should_skip_keyword(keyword_id, log.modifier_process_log)
            if (not should_skip_keyword and
                    keyword['average_position'] > maximum_position and
                    keyword['click_assisted_conversions'] < required_conversions):
                api_adapter.set_keyword_paused(keyword['ad_group_id'], keyword_id)
                if log is not None:
                    log.log_paused_keyword(keyword_id, max_cpc, modifier_data=modifier_data)
            elif log is not None:
                log.log_ignored_keyword(keyword_id, max_cpc, modifier_data=modifier_data)
