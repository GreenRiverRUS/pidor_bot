import os
import json
from random import choice
import time
import functools
from datetime import datetime, timedelta
import logging

from telegram.ext import Updater, CommandHandler  # MessageHandler, filters
from telegram.chat import Chat

from phrases import (
    GAME_RULES,
    common_phrases,
    scan_phrases,
    stats_phrases
)


SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
logging.basicConfig(format='%(levelname)s [%(asctime)s] %(message)s', level=logging.INFO)


def requires_public_chat(func):
    @functools.wraps(func)
    def wrapped(self, bot, update, **kwargs):
        chat = update.message.chat
        if chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
            func(self, bot, update, **kwargs)
        else:
            Bot.send_answer(bot, chat.id, 'access_denied')
    return wrapped


def logged(func):
    @functools.wraps(func)
    def wrapped(self, bot, update, **kwargs):
        chat = update.message.chat
        user_id = update.message.from_user.id
        logging.info('[Chat: {}] Get command "{}" from user {}'.format(
            chat.id,
            func.__name__,
            Bot.get_username(chat, user_id)
        ))
        func(self, bot, update, **kwargs)
    return wrapped


class Bot:
    def __init__(self, token, memory_filename):
        logging.info('Initializing bot...')
        self.updater = Updater(token=token)
        logging.info('Updater initialized')

        self.memory_filename = memory_filename
        self.memory = self.load_memory()
        logging.info('Memory loaded')

        self.today = None
        # self.echo_mode = False

        handlers = [
            CommandHandler('start', self.start),
            CommandHandler('pidorules', self.start),
            CommandHandler('shrug', self.shrug),
            CommandHandler('pidoreg', self.reg),
            CommandHandler('pidunreg', self.unreg),
            CommandHandler('pidor', self.choose_winner),
            CommandHandler('pidostats', self.stats),
            CommandHandler('all', self.list_players),
            # CommandHandler('echo', self.echo),
            # MessageHandler(filters.Filters.all, self.echo_msg)
        ]

        for handler in handlers:
            self.updater.dispatcher.add_handler(handler)
        self.updater.dispatcher.add_error_handler(self.error_handler)
        logging.info('Handlers added')

    def start_polling(self):
        logging.info('Start polling...')
        self.updater.start_polling()

    # noinspection PyUnusedLocal
    @staticmethod
    def error_handler(bot, update, telegram_error):
        chat = update.message.chat
        logging.error('[Chat: {}] Got error {}: {}'.format(chat.id, type(telegram_error), telegram_error))

    def load_memory(self):
        try:
            with open(self.memory_filename, 'r') as f:
                raw_memory = json.load(f)
        except IOError:
            raw_memory = {}
        logging.info('Loading memory for {} chats...'.format(len(raw_memory)))
        memory = {}
        for chat_id, chat_memory in raw_memory.items():
            chat_memory['players'] = set(chat_memory['players'])
            memory[int(chat_id)] = chat_memory
        return memory

    def get_memory(self, chat_id):
        return self.memory.setdefault(chat_id, {'players': set(), 'winners': {}})

    def commit_memory(self):
        def default(obj):
            if isinstance(obj, set):
                return list(obj)
            return json.JSONEncoder().default(obj)

        with open(self.memory_filename, 'w') as f:
            json.dump(self.memory, f, default=default)
        logging.info('Memory committed')

    def get_players(self, chat_id):
        return list(self.get_memory(chat_id)['players'])

    def add_player(self, chat_id, user_id):
        memory = self.get_memory(chat_id)
        memory['players'].add(user_id)
        logging.info('[Chat: {}] Updated players list: {}'.format(chat_id, list(memory['players'])))
        self.commit_memory()

    def remove_player(self, chat_id, user_id):
        memory = self.get_memory(chat_id)
        memory['players'].remove(user_id)
        logging.info('[Chat: {}] Updated players list: {}'.format(chat_id, list(memory['players'])))
        self.commit_memory()

    @staticmethod
    def get_current_date():
        return str((datetime.utcnow() + timedelta(hours=3)).date())

    def get_current_winner(self, chat_id):
        self.today = self.get_current_date()
        memory = self.get_memory(chat_id)
        winners = memory['winners']
        return winners.get(self.today, None)

    def set_current_winner(self, chat_id, user_id):
        if self.today is None:
            self.today = self.get_current_date()
        memory = self.get_memory(chat_id)
        winners = memory['winners']
        winners[self.today] = user_id
        logging.info('[Chat: {}] Updated winners: {}'.format(chat_id, winners))
        self.commit_memory()

    def get_top_winners_of_the_month(self, chat_id):
        current_month = self.get_current_date()[:-3]
        winners_by_date = filter(lambda x: x[0].startswith(current_month),
                                 self.get_memory(chat_id)['winners'].items())
        winners_by_id = {}
        for date, user_id in winners_by_date:
            winners_by_id.setdefault(user_id, []).append(date)
        logging.info(winners_by_id)
        sorted_winners = sorted(winners_by_id.items(), key=lambda x: (-len(x[1]), min(x[1])))
        return list(map(lambda x: (x[0], len(x[1])), sorted_winners))[:10]

    @staticmethod
    def get_username(chat, user_id, call=True):
        user = chat.get_member(user_id).user
        username = user.username
        if username != '':
            username = '{}{}'.format('@' if call else '', username)
        else:
            username = user.first_name or user.last_name or user_id
        return username

    @logged
    def start(self, bot, update):
        self.send_answer(bot, update.message.chat_id, text=GAME_RULES)

    @logged
    @requires_public_chat
    def stats(self, bot, update):
        message = update.message
        chat = message.chat
        winners = self.get_top_winners_of_the_month(chat.id)

        if len(winners) > 0:
            text = [stats_phrases['header'], '']
            for i, (winner_id, victories_cnt) in enumerate(winners):
                text.append(stats_phrases['template'].format(num=i + 1,
                                                             name=self.get_username(chat, winner_id, call=False),
                                                             cnt=victories_cnt))
            text += ['', stats_phrases['footer'].format(players_cnt=len(self.get_players(chat.id)))]
            self.send_answer(bot, chat.id, text='\n'.join(text))
        else:
            self.send_answer(bot, chat.id, template='no_winners')

    @logged
    @requires_public_chat
    def list_players(self, bot, update):
        message = update.message
        chat = message.chat
        players = self.get_players(chat.id)
        if len(players) > 0:
            for i in range(0, len(players), 10):
                players = [self.get_username(chat, player_id) for player_id in players[i:i+10]]
                text = ' '.join(players)
                if i == 0:
                    header = common_phrases['list_players_header']
                    text = '{}\n{}'.format(header, text)
                self.send_answer(bot, chat.id, text=text)
        else:
            self.send_answer(bot, chat.id, template='no_players')

    @logged
    @requires_public_chat
    def reg(self, bot, update):
        message = update.message
        chat = message.chat
        user_id = message.from_user.id
        if user_id in self.get_players(chat.id):
            answer_template = 'already_in_the_game'
        else:
            self.add_player(chat.id, user_id)
            answer_template = 'added_to_the_game'
        self.send_answer(bot, chat.id, template=answer_template)

    @logged
    @requires_public_chat
    def unreg(self, bot, update):
        message = update.message
        chat = message.chat
        user_id = message.from_user.id
        if user_id not in self.get_players(chat.id):
            answer_template = 'not_in_the_game'
        else:
            self.remove_player(chat.id, user_id)
            answer_template = 'removed_from_the_game'
        self.send_answer(bot, chat.id, template=answer_template)

    @logged
    @requires_public_chat
    def choose_winner(self, bot, update):
        message = update.message
        chat = message.chat
        current_winner = self.get_current_winner(chat.id)

        if current_winner is not None:
            username = self.get_username(message.chat, user_id=current_winner)
            self.send_answer(bot, chat.id, template='winner_known', name=username)
        else:
            players = self.get_players(chat.id)
            if len(players) == 0:
                self.send_answer(bot, chat.id, template='no_players')
            elif len(players) == 1:
                self.send_answer(bot, chat.id, template='only_one_player')
            else:
                for i in range(3):
                    phrase = choice(scan_phrases[i])
                    self.send_answer(bot, chat.id, text=phrase)
                    time.sleep(1.5)
                selected = choice(players)
                self.set_current_winner(chat.id, selected)
                selected_name = self.get_username(message.chat, user_id=selected)
                last_phrase = choice(scan_phrases[-1]).format(name=selected_name)
                self.send_answer(bot, chat.id, text=last_phrase)

    @logged
    def shrug(self, bot, update):
        self.send_answer(bot, update.message.chat_id, text='¯\_(ツ)_/¯')

    # def echo(self, bot, update):
    #     chat = update.message.chat
    #     user_id = update.message.from_user.id
    #     logging.info('[Chat: {}] Get command "chat" from user {}'.format(chat.id, self.get_username(chat, user_id)))
    #     if chat.id == 122377527:
    #         if self.echo_mode:
    #             self.send_answer(bot, chat.id, template='echo_finished')
    #             self.echo_mode = False
    #         else:
    #             self.send_answer(bot, chat.id, template='echo_started')
    #             self.echo_mode = True

    # def echo_msg(self, bot, update):
    #     message = update.message
    #     chat = message.chat
    #     if chat.id == 122377527 and self.echo_mode:
    #         self.send_answer(bot, -151166400, text=message.text)

    @staticmethod
    def send_answer(bot, chat_id, template=None, text=None, **kwargs):
        if text is None:
            text = common_phrases[template].format(**kwargs)
        logging.info('[Chat: {}] Sending response: {}'.format(chat_id, text))
        bot.sendMessage(chat_id=chat_id, text=text, parse_mode='html')


if __name__ == '__main__':
    with open(os.path.join(SCRIPT_DIR, 'token.txt')) as token_file:
        token_ = token_file.readline().strip()
    mem_filename = os.path.join(os.environ.get('MEMORY_DIR', SCRIPT_DIR), 'memory_dump.json')
    bot_ = Bot(token=token_, memory_filename=mem_filename)
    bot_.start_polling()
