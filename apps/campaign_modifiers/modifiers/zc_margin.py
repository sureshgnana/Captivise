from ..utils import ModifierBase


class ZeroClicksMargin(ModifierBase):
    name = 'zc based on margin'  # TODO:  What does that stand for?

    def run(self, api_adapter, adwords_campaign_id, target_cpa, log=None, **kwargs):
        keywords = list(
            api_adapter.get_keywords_for_campaign(adwords_campaign_id, enabled_only=True))

        average_cpa = sum(keyword['cpa'] for keyword in keywords) / len(keywords)
        keywords = (keyword for keyword in keywords if keyword['cost'] >= 2 * average_cpa)

        for keyword in keywords:
            keyword_id = keyword['id']

            modifier_data = {
                'target_cpa': target_cpa,
                'max_cpc': keyword['max_cpc'],
            }

            should_skip_keyword = self.should_skip_keyword(keyword_id, log.modifier_process_log)
            if not should_skip_keyword:
                api_adapter.set_keyword_paused(keyword['ad_group_id'], keyword_id)
                if log is not None:
                    log.log_paused_keyword(
                        keyword_id, keyword['max_cpc'], modifier_data=modifier_data)
            elif log is not None:
                log.log_ignored_keyword(
                    keyword_id, keyword['max_cpc'], modifier_data=modifier_data)
