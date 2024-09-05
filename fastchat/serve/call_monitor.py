import json
import os
import glob
import time

from fastapi import FastAPI
import hashlib
import asyncio

REFRESH_INTERVAL_SEC = 300
LOG_DIR_LIST = [
    "/home/gcpuser/fastchat_logs/server0",
    "/home/gcpuser/fastchat_logs/server1",
    "/home/gcpuser/fastchat_logs/server2",
    "/home/gcpuser/fastchat_logs/server3",
    "/home/gcpuser/fastchat_logs/server4",
    "/home/gcpuser/fastchat_logs/server5",
    "/home/gcpuser/fastchat_logs/server6",
    "/home/gcpuser/fastchat_logs/server7",
    "/home/gcpuser/fastchat_logs/server8",
    "/home/gcpuser/fastchat_logs/server9",
    "/home/gcpuser/fastchat_logs/server10",
    "/home/gcpuser/fastchat_logs/server11",
    "/home/gcpuser/fastchat_logs/server12",
    "/home/gcpuser/fastchat_logs/server13",
    "/home/gcpuser/fastchat_logs/server14",
    "/home/gcpuser/fastchat_logs/server15",
    "/home/gcpuser/fastchat_logs/server16",
    "/home/gcpuser/fastchat_logs/server17",
]
# LOG_DIR = "/home/vicuna/tmp/test_env"


class Monitor:
    """Monitor the number of calls to each model."""

    def __init__(self, log_dir_list: list):
        self.log_dir_list = log_dir_list
        self.model_call = {}
        self.user_call = {}
        self.model_call_limit_global = {
            "gpt-4-1106-preview": 100,
            "gpt-4-0125-preview": 100,
            "gpt-4-turbo-browsing": 200,
            "gpt-4-turbo-2024-04-09": 100,
            "mistral-large-2402": 200,
            "llama-3-70b-instruct": 2000,
            "claude-3-opus-20240229": 1000,
            "claude-3-sonnet-20240229": 1000,
            "dbrx-instruct": 1000,
            "command-r-plus": 1000,
            "gemini-1.5-pro-api-0409-preview": 1000,
            "gemini-1.5-pro-api-preview": 1000,
            "gpt2-chatbot": 1000,
            "im-a-good-gpt2-chatbot": 3000,
            "im-also-a-good-gpt2-chatbot": 3000,
            "gpt-4o-2024-05-13": 1000,
            "gpt-4o-2024-08-06": 1000,
            "yi-large": 300,
            "deepseek-coder-v2": 500,
            "deepseek-v2-api-0628": 300,
            "claude-3-5-sonnet-20240620": 2000,
            "experimental-mf-router": 100,
            "experimental-causal-router": 100,
            "llama-3.1-405b-instruct": 2000,
            "gemini-1.5-pro-exp-0801": 800,
            "sus-column-r": 3000,
            "chatgpt-4o-latest": 3000,
        }
        self.model_call_day_limit_per_user = {
            "gpt-4-1106-preview": 5,
            "gpt-4-0125-preview": 5,
            "gpt-4-turbo-2024-04-09": 5,
            "gpt-4-turbo-browsing": 8,
            "mistral-large-2402": 8,
            "claude-3-opus-20240229": 15,
            "claude-3-sonnet-20240229": 32,
            "command-r-plus": 32,
            "gemini-1.5-pro-api-0409-preview": 16,
            "gemini-1.5-pro-api-preview": 16,
            "gpt2-chatbot": 8,
            "im-a-good-gpt2-chatbot": 16,
            "im-also-a-good-gpt2-chatbot": 16,
            "gpt-4o-2024-05-13": 8,
            "gpt-4o-2024-08-06": 8,
            "deepseek-coder-v2": 16,
            "claude-3-5-sonnet-20240620": 16,
            "llama-3.1-405b-instruct": 16,
            "gemini-1.5-pro-exp-0801": 8,
            "sus-column-r": 16,
            "chatgpt-4o-latest": 16,
        }

    async def update_stats(self, num_file=1) -> None:
        while True:
            # find the latest num_file log under log_dir
            json_files = []
            for log_dir in self.log_dir_list:
                json_files_per_server = glob.glob(os.path.join(log_dir, "*.json"))
                json_files_per_server.sort(key=os.path.getctime, reverse=True)
                json_files += json_files_per_server[:num_file]
            model_call = {}
            user_call = {}
            for json_file in json_files:
                for line in open(json_file, "r", encoding="utf-8"):
                    obj = json.loads(line)
                    if obj["type"] != "chat":
                        continue
                    if obj["model"] not in model_call:
                        model_call[obj["model"]] = []
                    model_call[obj["model"]].append(
                        {"tstamp": obj["tstamp"], "user_id": obj["ip"]}
                    )
                    if obj["ip"] not in user_call:
                        user_call[obj["ip"]] = []
                    user_call[obj["ip"]].append(
                        {"tstamp": obj["tstamp"], "model": obj["model"]}
                    )

            self.model_call = model_call
            self.model_call_stats_hour = self.get_model_call_stats(top_k=None)
            self.model_call_stats_day = self.get_model_call_stats(
                top_k=None, most_recent_min=24 * 60
            )

            self.user_call = user_call
            self.user_call_stats_hour = self.get_user_call_stats(top_k=None)
            self.user_call_stats_day = self.get_user_call_stats(
                top_k=None, most_recent_min=24 * 60
            )
            await asyncio.sleep(REFRESH_INTERVAL_SEC)

    def get_model_call_limit(self, model: str) -> int:
        if model not in self.model_call_limit_global:
            return -1
        return self.model_call_limit_global[model]

    def update_model_call_limit(self, model: str, limit: int) -> bool:
        if model not in self.model_call_limit_global:
            return False
        self.model_call_limit_global[model] = limit
        return True

    def is_model_limit_reached(self, model: str) -> bool:
        if model not in self.model_call_limit_global:
            return False
        if model not in self.model_call_stats_hour:
            return False
        # check if the model call limit is reached
        if self.model_call_stats_hour[model] >= self.model_call_limit_global[model]:
            return True
        return False

    def is_user_limit_reached(self, model: str, user_id: str) -> bool:
        if model not in self.model_call_day_limit_per_user:
            return False
        if user_id not in self.user_call_stats_day:
            return False
        if model not in self.user_call_stats_day[user_id]["call_dict"]:
            return False
        # check if the user call limit is reached
        if (
            self.user_call_stats_day[user_id]["call_dict"][model]
            >= self.model_call_day_limit_per_user[model]
        ):
            return True
        return False

    def get_model_call_stats(
        self, target_model=None, most_recent_min: int = 60, top_k: int = 20
    ) -> dict:
        model_call_stats = {}
        for model, reqs in self.model_call.items():
            if target_model is not None and model != target_model:
                continue
            model_call = []
            for req in reqs:
                if req["tstamp"] < time.time() - most_recent_min * 60:
                    continue
                model_call.append(req["tstamp"])
            model_call_stats[model] = len(model_call)
        if top_k is not None:
            top_k_model = sorted(
                model_call_stats, key=lambda x: model_call_stats[x], reverse=True
            )[:top_k]
            model_call_stats = {model: model_call_stats[model] for model in top_k_model}
        return model_call_stats

    def get_user_call_stats(
        self, target_model=None, most_recent_min: int = 60, top_k: int = 20
    ) -> dict:
        user_call_stats = {}
        for user_id, reqs in self.user_call.items():
            user_model_call = {"call_dict": {}}
            for req in reqs:
                if req["tstamp"] < time.time() - most_recent_min * 60:
                    continue
                if target_model is not None and req["model"] != target_model:
                    continue
                if req["model"] not in user_model_call["call_dict"]:
                    user_model_call["call_dict"][req["model"]] = 0
                user_model_call["call_dict"][req["model"]] += 1

            user_model_call["total_calls"] = sum(user_model_call["call_dict"].values())
            if user_model_call["total_calls"] > 0:
                user_call_stats[user_id] = user_model_call
        if top_k is not None:
            top_k_user = sorted(
                user_call_stats,
                key=lambda x: user_call_stats[x]["total_calls"],
                reverse=True,
            )[:top_k]
            user_call_stats = {
                user_id: user_call_stats[user_id] for user_id in top_k_user
            }
        return user_call_stats

    def get_num_users(self, most_recent_min: int = 60) -> int:
        user_call_stats = self.get_user_call_stats(
            most_recent_min=most_recent_min, top_k=None
        )
        return len(user_call_stats)


monitor = Monitor(log_dir_list=LOG_DIR_LIST)
app = FastAPI()


@app.on_event("startup")
async def app_startup():
    asyncio.create_task(monitor.update_stats(2))


@app.get("/get_model_call_limit/{model}")
async def get_model_call_limit(model: str):
    return {"model_call_limit": {model: monitor.get_model_call_limit(model)}}


@app.get("/update_model_call_limit/{model}/{limit}")
async def update_model_call_limit(model: str, limit: int):
    if not monitor.update_model_call_limit(model, limit):
        return {"success": False}
    return {"success": True}


@app.get("/is_limit_reached")
async def is_limit_reached(model: str, user_id: str):
    if monitor.is_model_limit_reached(model):
        return {
            "is_limit_reached": True,
            "reason": f"MODEL_HOURLY_LIMIT ({model}): {monitor.get_model_call_limit(model)}",
        }
    if monitor.is_user_limit_reached(model, user_id):
        return {
            "is_limit_reached": True,
            "reason": f"USER_DAILY_LIMIT ({model}): {monitor.model_call_day_limit_per_user[model]}",
        }
    return {"is_limit_reached": False}


@app.get("/get_num_users_hr")
async def get_num_users():
    return {"num_users": len(monitor.user_call_stats_hour)}


@app.get("/get_num_users_day")
async def get_num_users_day():
    return {"num_users": len(monitor.user_call_stats_day)}


@app.get("/get_user_call_stats")
async def get_user_call_stats(
    model: str = None, most_recent_min: int = 60, top_k: int = None
):
    return {
        "user_call_stats": monitor.get_user_call_stats(model, most_recent_min, top_k)
    }


@app.get("/get_model_call_stats")
async def get_model_call_stats(
    model: str = None, most_recent_min: int = 60, top_k: int = None
):
    return {
        "model_call_stats": monitor.get_model_call_stats(model, most_recent_min, top_k)
    }
