#!/usr/bin/env python3

import json
import logging
import os
import sys
import yaml
import requests
from pprint import pprint

LOG_LEVEL = logging.DEBUG

logger = logging.getLogger("heroesprofile-filter-logger")
file_handler = logging.FileHandler('/tmp/heroesprofile-filter.log')
term_handler = logging.StreamHandler()

logger.setLevel(LOG_LEVEL)
file_handler.setLevel(LOG_LEVEL)
term_handler.setLevel(LOG_LEVEL)

formatter = logging.Formatter('[%(asctime)s]: %(levelname)s:\t%(message)s')
file_handler.setFormatter(formatter)
term_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(term_handler)

GAME_TYPES = {
    "qm": "Quick Match",
    "sl": "Storm League",
    "ud": "Unranked Draft",
    "aram": "ARAM",
}

class BattleTag:
    def __init__(
        self,
        battletag,
        api_token = None,
        api_token_path = None,
        base_url = None,
        mode = None,
        region = None,
        game_type = None,
    ):
        self.battletag = battletag
        self.api_token = api_token
        self.api_token_path = api_token_path
        self.base_url = base_url
        self.mode = mode
        self.region = region
        self.game_type = game_type

    def download_base_replays(self):
        params = self._params()
        username = self.battletag.split('#')[0]
        base_dir = f"{username}/base"
        os.makedirs(base_dir, exist_ok=True)

        for game_type in GAME_TYPES:
            base_file = f"{base_dir}/{game_type}"

            if not os.path.exists(base_file) or not os.path.isfile(base_file):
                logger.info(f"Downloading base replays for user '{username}', game_type '{game_type}.")
                # download base replays
                res = requests.get(
                    f"{self.base_url}/Player/Replays",
                    params={**params, "game_type": GAME_TYPES[game_type]},
                )
                assert res.status_code == 200
                with open(base_file, "w") as fd:
                    json.dump(obj=res.json(), fp=fd, indent=2)

            # open base replays file and verify its content is in valid JSON format
            try:
                with open(base_file, "r") as fd:
                    json_data = json.load(fd)
            except (json.JSONDecodeError, FileNotFoundError):
                logger.error(f"{base_file}: not a valid JSON format of the content!")
                sys.exit(1)

    def download_advanced_replays(self):
        params = self._params()
        username = self.battletag.split('#')[0]
        base_dir = f"{username}/base"
        adv_dir = f"{username}/advanced"
        os.makedirs(adv_dir, exist_ok=True)

        for game_type in GAME_TYPES:
            replays_cnt = 0
            logger.info(f"Downloading advanced replays for user '{username}', game_type '{game_type}'")
            base_file = f"{base_dir}/{game_type}"
            adv_file = f"{adv_dir}/{game_type}"

            # load all currently downloaded advanced replays into into dictionary
            with open(adv_file, "a+") as fda:
                fda.seek(0)
                adv_json = fda.read()
                if adv_json:
                    adv_json = json.loads(adv_json)
                else:
                    adv_json = dict()

            # continue downloading new advanced replays
            with open(base_file, "r") as fdb, open(adv_file, "w") as fda:
                base_json = json.load(fdb)
                if not base_json:
                    json.dump(obj=adv_json, fp=fda, indent=2)
                    logger.info(f"No replays exist for: username={username}, game_type '{game_type}.")
                    continue

                for replay_id in base_json[GAME_TYPES[game_type]]:
                    if replay_id in adv_json:
                        continue
                    res = requests.get(
                        f"{self.base_url}/Replay/Data",
                        params={
                            "mode": params["mode"],
                            "api_token": params["api_token"],
                            "replayID": replay_id,
                        },
                    )
                    if res.status_code == 200:
                        adv_json[replay_id] = res.json()[replay_id]
                        replays_cnt += 1
                    else:
                        logger.error(f"Unable to download advanced replay (id={replay_id}, username={username}, game_type '{game_type})")
                        logger.error(f"{res.__dict__}")
                        break

                json.dump(obj=adv_json, fp=fda, indent=2)
                if replays_cnt == 0:
                    logger.info(f"All replays are already downloaded for: username={username}, game_type '{game_type}")
                else:
                    logger.info(f"Advanced replays downloaded: {replays_cnt}")
            

    def _params(self, expand=True):
        params = {
            param: getattr(self, param)
            for param in
            ["mode", "region", "game_type", "battletag", "api_token"]
        }
        if expand:
            if params["game_type"] == "all":
               params["game_type"] = list(GAME_TYPES.values())
            elif not isinstance(params["game_type"], list):
                params["game_type"] = [params["game_type"]]
        return params


class BattleTags:
    config_path = "./config.yml"
    config_content = None
    battle_tags = []

    @classmethod
    def download_advanced_replays(cls):
        cls.read_config()
        cls.setup_battle_tags_from_config()

        for battle_tag in cls.battle_tags:
            battle_tag.download_base_replays()
            battle_tag.download_advanced_replays()
            
            
    @classmethod
    def read_config(cls):
        if cls.config_content is not None:
            return
        assert os.path.isfile(cls.config_path)

        with open(cls.config_path) as stream:
            try:
                cls.config_content = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                logger.error(exc)
                sys.exit(1)

    @classmethod
    def setup_battle_tags_from_config(cls):
        assert "general" in cls.config_content
        for tag in cls.config_content.get("battle_tags", []):
            cls.battle_tags.append(BattleTag(tag))
            tag_obj = cls.battle_tags[-1]
            for ppty in [
                "api_token_path",
                "base_url",
                "mode",
                "region",
                "game_type",
            ]: 
                if ppty in cls.config_content.get("general", []):
                    setattr(tag_obj, ppty, cls.config_content["general"][ppty])
                if isinstance(tag, list) and ppty in tag:
                    setattr(tag_obj, ppty, cls.config_content["battle_tags"][tag][ppty])
                if ppty == "api_token_path":
                    assert os.path.isfile(tag_obj.api_token_path)
                    with open(tag_obj.api_token_path) as fd:
                        tag_obj.api_token = fd.read().strip()
            

if __name__ == "__main__":
    logger.info("Starting heroesprofile-filter script")
    BattleTags.download_advanced_replays()
    logger.info("-" * 80)
