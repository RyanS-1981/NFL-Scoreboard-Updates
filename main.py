from PIL import Image, ImageFont, ImageDraw, ImageSequence
from rgbmatrix import graphics
from utils import center_text
from calendar import month_abbr
from renderer.screen_config import screenConfig
from datetime import datetime, timedelta
import time as t
import debug
import re

GAMES_REFRESH_RATE = 900.0

# -------------------- USER CONFIG --------------------
USER_SCALE = 2.0             # 1.0 = default 64x32 resolution
GRAPHICS_X_OFFSET = 0        # X offset for graphics/logos/animations
GRAPHICS_Y_OFFSET = 0        # Y offset for graphics/logos/animations
TEXT_X_OFFSET = 0            # X offset for text
TEXT_Y_OFFSET = 0            # Y offset for text
# -----------------------------------------------------

class MainRenderer:
    def __init__(self, matrix, data):
        self.matrix = matrix
        self.data = data
        self.screen_config = screenConfig("64x32_config")
        # Scaled canvas dimensions
        self.base_width = 64
        self.base_height = 32
        self.width = int(self.base_width * USER_SCALE)
        self.height = int(self.base_height * USER_SCALE)
        # Canvas
        self.canvas = matrix.CreateFrameCanvas()
        self.image = Image.new('RGB', (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)
        # Dynamic fonts
        self.font = self._get_scaled_font("fonts/score_large.otf", 16)
        self.font_mini = self._get_scaled_font("fonts/04B_24__.TTF", 8)

    # -------------------- FONT HELPERS --------------------
    def _get_scaled_font(self, font_path, base_size):
        scaled_size = int(base_size * USER_SCALE)
        return ImageFont.truetype(font_path, scaled_size)

    def _fit_text_font(self, text, font_path, base_size, max_width):
        font_size = int(base_size * USER_SCALE)
        font = ImageFont.truetype(font_path, font_size)
        text_width, _ = self.draw.textsize(text, font=font)
        while text_width > max_width and font_size > 1:
            font_size -= 1
            font = ImageFont.truetype(font_path, font_size)
            text_width, _ = self.draw.textsize(text, font=font)
        return font

    # -------------------- HELPERS --------------------
    def _scale_graphics_pos(self, x, y):
        return int(x * USER_SCALE + GRAPHICS_X_OFFSET), int(y * USER_SCALE + GRAPHICS_Y_OFFSET)

    def _scale_text_pos(self, text_width, y):
        scaled_x = int((self.width - text_width) / 2 + TEXT_X_OFFSET)
        scaled_y = int(y * USER_SCALE + TEXT_Y_OFFSET)
        return scaled_x, scaled_y

    def _scale_size(self, size):
        return int(size * USER_SCALE)

    # -------------------- RENDER LOOP --------------------
    def render(self):
        while True:
            self.starttime = t.time()
            self.data.get_current_date()
            self.__render_game()

    def __render_game(self):
        while True:
            if self.data.needs_refresh:
                self.data.refresh_games()
            self.__draw_game(self.data.current_game())
            refresh_rate = self.data.config.scrolling_speed
            t.sleep(refresh_rate)
            endtime = t.time()
            time_delta = endtime - self.starttime
            rotate_rate = self.__rotate_rate_for_game(self.data.current_game())
            if time_delta >= rotate_rate:
                self.starttime = t.time()
                self.data.needs_refresh = True
                if self.__should_rotate_to_next_game(self.data.current_game()):
                    game = self.data.advance_to_next_game()
                if endtime - self.data.games_refresh_time >= GAMES_REFRESH_RATE:
                    self.data.refresh_games()
                if self.data.needs_refresh:
                    self.data.refresh_games()

    def __rotate_rate_for_game(self, game):
        rotate_rate = self.data.config.rotation_rates_live
        if game['state'] == 'pre':
            rotate_rate = self.data.config.rotation_rates_pregame
        if game['state'] == 'post':
            rotate_rate = self.data.config.rotation_rates_final
        return rotate_rate

    def __should_rotate_to_next_game(self, game):
        if not self.data.config.rotation_enabled:
            return False
        stay_on_preferred_team = self.data.config.preferred_teams and not self.data.config.rotation_preferred_team_live_enabled
        return not stay_on_preferred_team

    def __draw_game(self, game):
        now = self.data.get_current_date()
        gametime = datetime.strptime(game['date'], "%Y-%m-%dT%H:%MZ")
        if now < gametime - timedelta(hours=1) and game['state'] == 'pre':
            self._draw_pregame(game)
        elif now < gametime and game['state'] == 'pre':
            self._draw_countdown(game)
        elif game['state'] == 'post':
            self._draw_post_game(game)
        else:
            self._draw_live_game(game)

    # -------------------- DRAW METHODS --------------------
    def _draw_pregame(self, game):
        gamedatetime = self.data.get_gametime()
        now = self.data.get_current_date()
        date_text = 'TODAY' if gamedatetime.day == now.day else gamedatetime.strftime('%A %-d %b').upper()
        gametime_text = gamedatetime.strftime("%-I:%M %p")

        date_font = self._fit_text_font(date_text, "fonts/04B_24__.TTF", 8, self.width - 4)
        gametime_font = self._fit_text_font(gametime_text, "fonts/04B_24__.TTF", 8, self.width - 4)

        date_pos = self._scale_text_pos(date_font.getsize(date_text)[0], 0)
        gametime_pos = self._scale_text_pos(gametime_font.getsize(gametime_text)[0], 6)
        vs_pos = self._scale_graphics_pos(25, 15)

        self.draw.text(date_pos, date_text, font=date_font, fill=(255, 255, 255))
        self.draw.multiline_text(gametime_pos, gametime_text, font=gametime_font, fill=(255, 255, 255), align="center")
        self.draw.text(vs_pos, "VS", font=self.font, fill=(255, 255, 255))

        away_logo = Image.open(f'logos/{game["awayteam"]}H.png').resize((self._scale_size(20), self._scale_size(20)))
        home_logo = Image.open(f'logos/{game["hometeam"]}H.png').resize((self._scale_size(20), self._scale_size(20))).transpose(Image.FLIP_LEFT_RIGHT)
        away_pos = self._scale_graphics_pos(1, 12)
        home_pos = self._scale_graphics_pos(43, 12)

        self.canvas.SetImage(self.image, 0, 0)
        self.canvas.SetImage(away_logo.convert("RGB"), *away_pos)
        self.canvas.SetImage(home_logo.convert("RGB"), *home_pos)
        self.canvas = self.matrix.SwapOnVSync(self.canvas)
        self.image = Image.new('RGB', (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

      # -------------------- COUNTDOWN --------------------

    def _draw_countdown(self, game):
        now = self.data.get_current_date()
        gametime = datetime.strptime(game['date'], "%Y-%m-%dT%H:%MZ")
        delta = gametime - now
        gametime_text = ':'.join(str(delta).split(':')[:2]) if delta > timedelta(hours=1) else ':'.join(str(delta).split(':')[1:]).split('.')[0]

        in_font = self._fit_text_font("IN", "fonts/04B_24__.TTF", 8, self.width - 4)
        gametime_font = self._fit_text_font(gametime_text, "fonts/04B_24__.TTF", 8, self.width - 4)

        in_pos = self._auto_center_text_pos("IN", in_font, 0.0)
        gametime_pos = self._auto_center_text_pos(gametime_text, gametime_font, 0.2)
        vs_pos = self._scale_graphics_pos(25, 15)

        self.draw.text(in_pos, "IN", font=in_font, fill=(255, 255, 255))
        self.draw.multiline_text(gametime_pos, gametime_text, font=gametime_font, fill=(255, 255, 255), align="center")
        self.draw.text(vs_pos, "VS", font=self.font, fill=(255, 255, 255))

        away_logo = Image.open(f'logos/{game["awayteam"]}.png').resize((self._scale_size(20), self._scale_size(20)))
        home_logo = Image.open(f'logos/{game["hometeam"]}.png').resize((self._scale_size(20), self._scale_size(20)))
        away_pos = self._scale_graphics_pos(1, 12)
        home_pos = self._scale_graphics_pos(43, 12)

        self.canvas.SetImage(self.image, 0, 0)
        self.canvas.SetImage(away_logo.convert("RGB"), *away_pos)
        self.canvas.SetImage(home_logo.convert("RGB"), *home_pos)
        self.canvas = self.matrix.SwapOnVSync(self.canvas)
        self.image = Image.new('RGB', (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

    # -------------------- LIVE GAME --------------------
    def _draw_live_game(self, game):
        homescore = game['homescore']
        awayscore = game['awayscore']
        if self.data.needs_refresh:
            self.data.refresh_games()
            self.data.needs_refresh = False

        pos_team = game['awayteam'] if game['possession'] == game['awayid'] else game['hometeam']
        down = re.sub(r"[a-z]+", "", game['down']).replace(" ", "") if game['down'] else None
        spot = game['spot'].replace(" ", "") if game['spot'] else None
        quarter = str(game['quarter'])
        time_period = game['time']

        # Vertical ratios
        info_y_down, info_y_spot, info_y_pos, info_y_quarter, info_y_time = 0.6, 0.75, 0.4, 0.0, 0.2

        if down:
            down_font = self._fit_text_font(down, "fonts/04B_24__.TTF", 8, self.width - 4)
            down_pos = self._auto_center_text_pos(down, down_font, info_y_down)
            self.draw.multiline_text(down_pos, down, fill=(255, 255, 255), font=down_font, align="center")

        if spot:
            spot_font = self._fit_text_font(spot, "fonts/04B_24__.TTF", 8, self.width - 4)
            spot_pos = self._auto_center_text_pos(spot, spot_font, info_y_spot)
            self.draw.multiline_text(spot_pos, spot, fill=(255, 255, 255), font=spot_font, align="center")

        pos_font = self._fit_text_font(pos_team, "fonts/04B_24__.TTF", 8, self.width - 4)
        pos_colour = (255, 25, 25) if game['redzone'] else (255, 255, 255)
        pos_pos = self._auto_center_text_pos(pos_team, pos_font, info_y_pos)
        self.draw.multiline_text(pos_pos, pos_team, fill=pos_colour, font=pos_font, align="center")

        quarter_font = self._fit_text_font(quarter, "fonts/04B_24__.TTF", 8, self.width - 4)
        time_font = self._fit_text_font(time_period, "fonts/04B_24__.TTF", 8, self.width - 4)
        quarter_pos = self._auto_center_text_pos(quarter, quarter_font, info_y_quarter)
        time_pos = self._auto_center_text_pos(time_period, time_font, info_y_time)
        self.draw.multiline_text(quarter_pos, quarter, fill=(255, 255, 255), font=quarter_font, align="center")
        self.draw.multiline_text(time_pos, time_period, fill=(255, 255, 255), font=time_font, align="center")

        homescore_text = '{0:02d}'.format(homescore)
        awayscore_text = '{0:02d}'.format(awayscore)
        away_score_pos = self._scale_graphics_pos(6, 19)
        home_score_pos = self._scale_graphics_pos(59 - self.font.getsize(homescore_text)[0], 19)
        self.draw.multiline_text(away_score_pos, awayscore_text, fill=(255, 255, 255), font=self.font, align="center")
        self.draw.multiline_text(home_score_pos, homescore_text, fill=(255, 255, 255), font=self.font, align="center")

        away_logo = Image.open(f'logos/{game["awayteam"]}H.png').resize((self._scale_size(20), self._scale_size(20)))
        home_logo = Image.open(f'logos/{game["hometeam"]}H.png').resize((self._scale_size(20), self._scale_size(20))).transpose(Image.FLIP_LEFT_RIGHT)
        away_pos = self._scale_graphics_pos(1, 0)
        home_pos = self._scale_graphics_pos(43, 0)

        self.canvas.SetImage(self.image, 0, 0)
        self.canvas.SetImage(away_logo.convert("RGB"), *away_pos)
        self.canvas.SetImage(home_logo.convert("RGB"), *home_pos)
        self.canvas = self.matrix.SwapOnVSync(self.canvas)
        self.image = Image.new('RGB', (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)
        self.data.needs_refresh = True

    # -------------------- POST GAME --------------------
    def _draw_post_game(self, game):
        score_text = f'{game["awayscore"]}-{game["homescore"]}'
        score_font = self._fit_text_font(score_text, "fonts/score_large.otf", 16, self.width - 4)
        score_pos = self._auto_center_text_pos(score_text, score_font, 0.6)

        end_font = self._fit_text_font("END", "fonts/04B_24__.TTF", 8, self.width - 4)
        end_pos = self._auto_center_text_pos("END", end_font, 0.2)

        self.draw.multiline_text(score_pos, score_text, fill=(255, 255, 255), font=score_font, align="center")
        self.draw.multiline_text(end_pos, "END", fill=(255, 255, 255), font=end_font, align="center")

        away_logo = Image.open(f'logos/{game["awayteam"]}.png').resize((self._scale_size(20), self._scale_size(20)))
        home_logo = Image.open(f'logos/{game["hometeam"]}.png').resize((self._scale_size(20), self._scale_size(20)))
        away_pos = self._scale_graphics_pos(1, 0)
        home_pos = self._scale_graphics_pos(43, 0)

        self.canvas.SetImage(self.image, 0, 0)
        self.canvas.SetImage(away_logo.convert("RGB"), *away_pos)
        self.canvas.SetImage(home_logo.convert("RGB"), *home_pos)
        self.canvas = self.matrix.SwapOnVSync(self.canvas)
        self.image = Image.new('RGB', (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

    # -------------------- ANIMATIONS --------------------
    def _draw_td(self):
        ball = Image.open("assets/td_ball.gif")
        words = Image.open("assets/td_words.gif")
        frameNo = 0
        self.canvas.Clear()

        def process_frame(frame):
            frame = frame.convert("RGB")
            frame = frame.resize((self.width, self.height))
            return frame

        for _ in range(3):
            try: ball.seek(frameNo)
            except EOFError: frameNo = 0; ball.seek(frameNo)
            frame = process_frame(ball)
            self.canvas.SetImage(frame, GRAPHICS_X_OFFSET, GRAPHICS_Y_OFFSET)
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            frameNo += 1
            t.sleep(0.05)

        frameNo = 0
        for _ in range(3):
            try: words.seek(frameNo)
            except EOFError: frameNo = 0; words.seek(frameNo)
            frame = process_frame(words)
            self.canvas.SetImage(frame, GRAPHICS_X_OFFSET, GRAPHICS_Y_OFFSET)
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            frameNo += 1
            t.sleep(0.05)

    def _draw_fg(self):
        im = Image.open("assets/fg.gif")
        frameNo = 0
        self.canvas.Clear()

        def process_frame(frame):
            frame = frame.convert("RGB")
            frame = frame.resize((self.width, self.height))
            return frame

        for _ in range(3):
            try: im.seek(frameNo)
            except EOFError: frameNo = 0; im.seek(frameNo)
            frame = process_frame(im)
            self.canvas.SetImage(frame, GRAPHICS_X_OFFSET, GRAPHICS_Y_OFFSET)
            self.canvas = self.matrix.SwapOnVSync(self.canvas)
            frameNo += 1
            t.sleep(0.02)
