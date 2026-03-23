from portfolio.models import Portfolio
def run():
    for p in Portfolio.objects.all():
        print(p.name)