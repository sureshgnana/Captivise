;$(function () {
  function hideTargetInputs () {
    $('#id_target_cpa').parent().hide();
    $('#id_target_conversion_margin').parent().hide();
  }
  hideTargetInputs();

  var checkedConversionType = $('#id_conversion_type :checked').val();
  if (checkedConversionType !== undefined) {
    $('#id_target_' + checkedConversionType).parent().show();
  }

  $('#id_conversion_type input').change(function () {
    hideTargetInputs();
    $('#id_target_' + $(this).val()).parent().show();
  });
});
