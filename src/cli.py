"""
TaskMasterAI CLI - コマンドラインインターフェース

ユーザーとの対話的なインターフェースを提供
"""

import sys
import logging
from pathlib import Path

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_banner():
    """起動バナーを表示"""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ████████╗ █████╗ ███████╗██╗  ██╗                      ║
║   ╚══██╔══╝██╔══██╗██╔════╝██║ ██╔╝                      ║
║      ██║   ███████║███████╗█████╔╝                       ║
║      ██║   ██╔══██║╚════██║██╔═██╗                       ║
║      ██║   ██║  ██║███████║██║  ██╗                      ║
║      ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝                      ║
║                                                           ║
║   ███╗   ███╗ █████╗ ███████╗████████╗███████╗██████╗    ║
║   ████╗ ████║██╔══██╗██╔════╝╚══██╔══╝██╔════╝██╔══██╗   ║
║   ██╔████╔██║███████║███████╗   ██║   █████╗  ██████╔╝   ║
║   ██║╚██╔╝██║██╔══██║╚════██║   ██║   ██╔══╝  ██╔══██╗   ║
║   ██║ ╚═╝ ██║██║  ██║███████║   ██║   ███████╗██║  ██║   ║
║   ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝   ║
║                                                           ║
║          🤖 AI-Powered Virtual Executive Assistant        ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)


def interactive_mode():
    """対話モードを起動"""
    from .coordinator import Coordinator

    print_banner()
    print("\nTaskMasterAI を起動しました。")
    print("'help' でコマンド一覧を表示、'quit' で終了します。\n")

    coordinator = Coordinator(
        audit_log_path="logs/audit_log.json"
    )

    while True:
        try:
            user_input = input("taskmaster> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("TaskMasterAI を終了します。お疲れさまでした！")
                break

            result = coordinator.process_command(user_input)
            print(result.message)
            print()

        except KeyboardInterrupt:
            print("\n\nTaskMasterAI を終了します。")
            break
        except Exception as e:
            logger.error(f"エラー: {e}")
            print(f"エラーが発生しました: {e}")


def single_command_mode(args: list[str]):
    """単一コマンドモード"""
    from .coordinator import Coordinator

    command = " ".join(args)
    coordinator = Coordinator()

    result = coordinator.process_command(command)
    print(result.message)

    return 0 if result.success else 1


def auth_mode():
    """認証モード"""
    from .email_bot import EmailBot
    from .scheduler import Scheduler

    print("Google API認証を開始します...")

    email_bot = EmailBot()
    scheduler = Scheduler()

    email_success = email_bot.authenticate()
    calendar_success = scheduler.authenticate()

    if email_success and calendar_success:
        print("✅ Gmail API認証成功")
        print("✅ Google Calendar API認証成功")
        print("\n認証が完了しました。TaskMasterAI を使用する準備ができました。")
        return 0
    else:
        print("❌ 認証に失敗しました。設定を確認してください。")
        print("詳細は docs/setup_google_api.md を参照してください。")
        return 1


def main():
    """メインエントリーポイント"""
    args = sys.argv[1:]

    if not args:
        # 引数なしは対話モード
        interactive_mode()
    elif args[0] == "auth":
        # 認証モード
        sys.exit(auth_mode())
    elif args[0] in ["-h", "--help"]:
        # ヘルプ
        print("""
TaskMasterAI - AI-Powered Virtual Executive Assistant

使用方法:
  python -m src.cli              対話モードを起動
  python -m src.cli auth         Google API認証を実行
  python -m src.cli <command>    単一コマンドを実行

コマンド例:
  python -m src.cli inbox
  python -m src.cli status
  python -m src.cli "schedule meeting with alice@example.com 30min"

詳細は 'help' コマンドで確認してください。
""")
    else:
        # 単一コマンドモード
        sys.exit(single_command_mode(args))


if __name__ == "__main__":
    main()
