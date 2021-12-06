from ..utils import ModifierBase


class LowClickThroughRate(ModifierBase):
    name = 'Low click through rate'

    def run(self, api_adapter, adwords_campaign_id, log=None, **kwargs):
        date_range = self.get_date_range_from_now(365)
        keywords = list(api_adapter.get_keywords_for_campaign(
            adwords_campaign_id, enabled_only=True, date_range=date_range))

        avg_ctr = sum([keyword['click_through_rate'] for keyword in keywords]) / len(keywords)
        avg_conv_rate = sum([keyword['conversion_rate'] for keyword in keywords]) / len(keywords)

        required_ctr = avg_ctr / 5
        required_conv_rate = avg_conv_rate / 5

        for keyword in keywords:
            keyword_id = keyword['id']
            max_cpc = keyword['max_cpc']

            modifier_data = {
                'avg_ctr': avg_ctr,
                'avg_conv_rate': avg_conv_rate,
                'required_ctr': required_ctr,
                'required_conv_rate': required_conv_rate,
                'max_cpc': max_cpc,
                'click_through_rate': keyword['click_through_rate'],
                'conversion_rate': keyword['conversion_rate'],
            }

            should_skip_keyword = self.should_skip_keyword(keyword_id, log.modifier_process_log)
            if (not should_skip_keyword and
                    keyword['click_through_rate'] < required_ctr and
                    keyword['conversion_rate'] < required_conv_rate):
                api_adapter.set_keyword_paused(keyword['ad_group_id'], keyword_id)
                if log is not None:
                    log.log_paused_keyword(keyword_id, max_cpc, modifier_data=modifier_data)
            elif log is not None:
                log.log_ignored_keyword(keyword_id, max_cpc, modifier_data=modifier_data)
