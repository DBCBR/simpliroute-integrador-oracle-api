
"""
Removido: script utilitário para depuração do token_manager.
Preservado como placeholder. Use o histórico Git para restaurar se necessário.
"""

def main():
    print('check_token_manager.py: removido — utilitário não essencial')

if __name__ == '__main__':
    main()


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
