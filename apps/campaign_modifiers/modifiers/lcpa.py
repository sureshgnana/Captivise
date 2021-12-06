from ..utils import ModifierBase


class LowCostPerAcquisitionModifier(ModifierBase):
    name = 'Low cost per acquisition'

    def run(self, api_adapter, adwords_campaign_id, target_cpa, max_cpc_limit, log=None, **kwargs):
        date_range = self.get_date_range_from_now(90)
        keywords = api_adapter.get_keywords_for_campaign(
            adwords_campaign_id, enabled_only=True, date_range=date_range)

        for keyword in keywords:
            keyword_id = keyword['id']
            cpa = keyword['cpa']
            max_cpc = keyword['max_cpc']

            modifier_data = {
                'cpa': cpa,
                'target_cpa': target_cpa,
                'max_cpc_limit': max_cpc_limit,
                'max_cpc': max_cpc,
            }

            should_skip_keyword = self.should_skip_keyword(keyword_id, log.modifier_process_log)
            if not should_skip_keyword and cpa < 0.8 * target_cpa:
                new_max_cpc = round(min(int(max_cpc * 1.2), max_cpc_limit), -4)

                modifier_data['new_max_cpc'] = new_max_cpc

                api_adapter.set_keyword_max_cpc(keyword['ad_group_id'], keyword_id, new_max_cpc)
                if log is not None:
                    if new_max_cpc > max_cpc:
                        log.log_increased_keyword_cpc(
                            keyword_id, max_cpc, new_max_cpc, modifier_data=modifier_data)
                    elif new_max_cpc < max_cpc:
                        log.log_decreased_keyword_cpc(
                            keyword_id, max_cpc, new_max_cpc, modifier_data=modifier_data)
                    else:
                        log.log_ignored_keyword(keyword_id, max_cpc, modifier_data=modifier_data)
            elif log is not None:
                log.log_ignored_keyword(keyword_id, max_cpc, modifier_data=modifier_data)
