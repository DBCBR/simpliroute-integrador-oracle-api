import asyncio
import sys
sys.path.insert(0, "/app")
from src.integrations.simpliroute import token_manager


async def main():
    tok = await token_manager.get_token()
    if not tok:
        print('NO_TOKEN')
        return
    # print only a prefix for safety
    preview = tok if len(tok) <= 60 else tok[:40] + '...'
    print('TOKEN_PREFIX:', preview)


if __name__ == '__main__':
    asyncio.run(main())
