import time

from django.core.management.base import BaseCommand

from shajara.matching import run_matching


class Command(BaseCommand):
    help = (
        "Shajaralar orasida bir xil shaxslarni qidiradi va admin uchun moslik nomzodlarini yangilaydi. "
        "--loop bilan fon jarayoni sifatida uzluksiz ishlaydi."
    )

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="To'xtatilmaguncha qayta-qayta ishlash")
        parser.add_argument("--interval", type=int, default=900, help="Yurishlar orasidagi soniyalar (standart 900)")

    def handle(self, *args, **options):
        while True:
            run = run_matching()
            self.stdout.write(
                f"[{run.finished_at:%Y-%m-%d %H:%M}] {run.persons_scanned} shaxs, "
                f"{run.pairs_compared} juftlik, {run.candidates_found} moslik ({run.candidates_new} yangi)"
            )
            if not options["loop"]:
                break
            time.sleep(max(60, options["interval"]))
