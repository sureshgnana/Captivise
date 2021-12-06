;$(function () {
  var remainder = $('.js-form-remainder')
  if ($('#id_is_managed :checked').val() === 'False') {
    remainder.hide();
  }

  $('#id_is_managed input').change(function () {
    var val = $(this).val();
    if (val === 'True') {
      remainder.show();
    } else if (val === 'False') {
      remainder.hide();
    }
  });
});
