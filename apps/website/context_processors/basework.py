from ..models import CmsContent


def cms_content_work(request):
    cms_content = CmsContent.objects.filter(show_in_menu=True, status=True)
    return {
        'cms_content': cms_content
    }
