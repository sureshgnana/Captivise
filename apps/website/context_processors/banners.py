def hidden_banners(request):
    hidden_banners = request.session.get('hidden_banners', [])

    return {
        'hide_{banner_name}'.format(banner_name=banner_name): True
        for banner_name in hidden_banners
    }
