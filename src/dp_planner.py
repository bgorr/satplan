import numpy as np
import random
from tqdm import tqdm


V = []
NQ = []

def close_enough(lat0,lon0,lat1,lon1):
    if np.sqrt((lat0-lat1)**2+(lon0-lon1)**2) < 0.01:
        return True
    else:
        return False

def propagate_weights(obs_list,settings):
    rewards = np.zeros(shape=(len(obs_list)))
    node_indices = [None]*len(obs_list)
    for i in range(len(obs_list)):
        rewards[i] = obs_list[i]["reward"]
        node_indices[i] = None
    for i in range(len(obs_list)):
        for k in range(len(obs_list)):
            feasible, transition_end_time = check_maneuver_feasibility(obs_list[i]["angle"],obs_list[k]["angle"],obs_list[i]["start"],obs_list[k]["end"],settings)
            if transition_end_time < obs_list[i]["start"]:
                obs_list[i]["soonest"] = obs_list[i]["end"]
            else:
                obs_list[i]["soonest"] = obs_list[i]["end"]
            if feasible and ((rewards[i]+obs_list[k]["reward"]) > rewards[k]) and obs_list[i]["soonest"] < obs_list[k]["start"]:
                rewards[k] = rewards[i] + obs_list[k]["reward"]
                node_indices[k] = i
    return rewards, node_indices

def extract_path(obs_list,rewards,node_indices):
    reverse_plan = []
    if not rewards.any():
        return []
    node_index = np.argmax(rewards)
    while node_index is not None:
        reverse_plan.append(obs_list[node_index])
        node_index = node_indices[node_index]
    plan = reversed(reverse_plan)
    return plan

def check_maneuver_feasibility(curr_angle,obs_angle,curr_time,obs_end_time,settings):
    """
    Checks to see if the specified angle change violates the maximum slew rate constraint.
    """
    moved = False
    # TODO add back FOV free visibility
    if(obs_end_time==curr_time):
        return False, False
    slew_rate = abs(obs_angle-curr_angle)/abs(obs_end_time-curr_time)/settings["step_size"]
    max_slew_rate = settings["agility"] # deg / s
    #slewTorque = 4 * abs(np.deg2rad(new_angle)-np.deg2rad(curr_angle))*0.05 / pow(abs(new_time-curr_time),2)
    #maxTorque = 4e-3
    transition_end_time = abs(obs_angle-curr_angle)/(max_slew_rate*settings["step_size"]) + curr_time
    moved = True
    return slew_rate < max_slew_rate, transition_end_time

def check_maneuver_feasibility_torque(curr_angle,obs_angle,curr_time,obs_end_time,settings):
    """
    Checks to see if the specified angle change violates the maximum slew rate constraint.
    """
    # TODO add back FOV free visibility
    if(obs_end_time==curr_time):
        return False, False
    obs_end_time = obs_end_time*settings["step_size"]
    curr_time = curr_time*settings["step_size"]
    inertia = 2.66
    slew_torque = 4 * abs(np.deg2rad(obs_angle)-np.deg2rad(curr_angle))*inertia / pow(abs(obs_end_time-curr_time),2)
    max_torque = 3e-4
    transition_end_time = (np.sqrt(4 * abs(np.deg2rad(obs_angle)-np.deg2rad(curr_angle))*inertia / max_torque) + curr_time)/settings["step_size"]
    return slew_torque < max_torque, transition_end_time

def graph_search(obs_list,settings):
    rewards, node_indices = propagate_weights(obs_list,settings)
    plan = extract_path(obs_list,rewards,node_indices)
    return list(plan)

def graph_search_events(planner_inputs):
    events = planner_inputs["events"]
    obs_list = planner_inputs["obs_list"]
    plan_start = planner_inputs["plan_start"] # TODO chop the search
    plan_end = planner_inputs["plan_end"]
    settings = planner_inputs["settings"]
    rewards, node_indices = propagate_weights(obs_list,settings)
    prelim_plan = list(extract_path(obs_list,rewards,node_indices))
    if len(prelim_plan) == 0:
        planner_outputs = {
            "plan": [],
            "end_time": plan_end,
            "updated_reward": None
        }
        return planner_outputs
    plan = []
    for next_obs in prelim_plan:
        plan.append(next_obs)
        curr_time = next_obs["soonest"]
        for event in events:
            if close_enough(next_obs["location"]["lat"],next_obs["location"]["lon"],event["location"]["lat"],event["location"]["lon"]):
                if (event["start"] <= next_obs["start"] <= event["end"]) or (event["start"] <= next_obs["end"] <= event["end"]):
                    updated_reward = { 
                        "reward": event["severity"]*settings["reward"],
                        "location": next_obs["location"],
                        "last_updated": curr_time 
                    }
                    planner_outputs = {
                        "plan": plan,
                        "end_time": curr_time,
                        "updated_reward": updated_reward
                    }
                    return planner_outputs
    planner_outputs = {
        "plan": plan,
        "end_time": plan_end,
        "updated_reward": None
    }
    return planner_outputs

def graph_search_events_interval(planner_inputs):
    events = planner_inputs["events"]
    obs_list = planner_inputs["obs_list"]
    plan_start = planner_inputs["plan_start"]
    plan_end = planner_inputs["plan_end"]
    sharing_end = planner_inputs["sharing_end"]
    settings = planner_inputs["settings"]
    orbitpy_id = planner_inputs["orbitpy_id"]
    rewards, node_indices = propagate_weights(obs_list,settings)
    prelim_plan = list(extract_path(obs_list,rewards,node_indices))
    updated_rewards = []
    if len(prelim_plan) == 0:
        planner_outputs = {
            "plan": [],
            "end_time": plan_end,
            "updated_rewards": updated_rewards
        }
        return planner_outputs
    plan = []
    for next_obs in prelim_plan:
        plan.append(next_obs)
        curr_time = next_obs["end"]
        not_in_event = True
        for event in events:
            if close_enough(next_obs["location"]["lat"],next_obs["location"]["lon"],event["location"]["lat"],event["location"]["lon"]):
                if (event["start"] <= next_obs["start"] <= event["end"]) or (event["start"] <= next_obs["end"] <= event["end"]) and next_obs["end"] < sharing_end:
                    updated_reward = { 
                        "reward": event["severity"]*settings["reward"],
                        "location": next_obs["location"],
                        "last_updated": curr_time,
                        "orbitpy_id": orbitpy_id
                    }
                    updated_rewards.append(updated_reward)
                    not_in_event = False
        if not_in_event and next_obs["end"] < sharing_end:
            updated_reward = {
                "reward": 0.0,
                "location": next_obs["location"],
                "last_updated": curr_time,
                "orbitpy_id": orbitpy_id
            }
            updated_rewards.append(updated_reward)
        if curr_time > plan_end:
            break
                    
    planner_outputs = {
        "plan": plan,
        "end_time": plan_end,
        "updated_rewards": updated_rewards
    }
    return planner_outputs