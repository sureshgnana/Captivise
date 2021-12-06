import decimal

from ..utils import ModifierBase


class TargetCostPerAcquisitionMargin(ModifierBase):
    name = 'Target cost per acquisition based on margin'

    def run(
            self,
            api_adapter,
            adwords_campaign_id,
            cycle_period,
            target_conversion_margin,
            max_cpc_limit,
            log=None,
            **kwargs):
        date_range = self.get_date_range_from_now(cycle_period)
        keywords = api_adapter.get_keywords_for_campaign(
            adwords_campaign_id, enabled_only=True, date_range=date_range)

        keywords = (keyword for keyword in keywords
                    if keyword['click_assisted_conversions'] >= 3)

        for keyword in keywords:
            keyword_id = keyword['id']
            max_cpc = keyword['max_cpc']

            modifier_data = {
                'cycle_period': cycle_period,
                'target_conversion_margin': target_conversion_margin,
                'max_cpc_limit': max_cpc_limit,
                'max_cpc': max_cpc,
                'conversion_rate': keyword['conversion_rate'],
            }

            should_skip_keyword = self.should_skip_keyword(keyword_id, log.modifier_process_log)
            if not should_skip_keyword:
                new_max_cpc = round(
                    int(min(
                        decimal.Decimal(
                            keyword['value_per_conversion'] * (target_conversion_margin / 100)
                        ) *
                        keyword['conversion_rate'], max_cpc_limit
                    )),
                    -4,
                )

                modifier_data['new_max_cpc'] = new_max_cpc

                api_adapter.set_keyword_max_cpc(keyword['ad_group_id'], keyword_id, new_max_cpc)

            if log is not None:
                if should_skip_keyword or new_max_cpc == max_cpc:
                    log.log_ignored_keyword(keyword_id, max_cpc, modifier_data=modifier_data)
                elif new_max_cpc > max_cpc:
                    log.log_increased_keyword_cpc(
                        keyword_id, max_cpc, new_max_cpc, modifier_data=modifier_data)
                elif new_max_cpc < max_cpc:
                    log.log_decreased_keyword_cpc(
                        keyword_id, max_cpc, new_max_cpc, modifier_data=modifier_data)
