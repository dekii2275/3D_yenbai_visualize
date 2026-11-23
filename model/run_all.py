"""Run the whole trial pipeline: dataset → susceptibility model → rain thresholds → backtest."""
import sys

from model import backtest, build_dataset, rain_thresholds, train_susceptibility


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    for name, step in [('1/4 Bộ dữ liệu', build_dataset.main), ('2/4 Mô hình dễ trượt', train_susceptibility.main),
                       ('3/4 Ngưỡng mưa nháp', rain_thresholds.main), ('4/4 Backtest', backtest.main)]:
        print(f'== {name}')
        step()


if __name__ == '__main__':
    main()
