from teamwork.conversation import Turn
import parse
import score
import random

# -------------------
# Utility Fcns
# -------------------

def parse_and_score(config, input_prompts, turn):

    # Given an LLM response in turn, parse the answer and score it
    
    if config.task_type == 'ranking':
        ans = parse.parse_ranking(turn.content, input_prompts["items"])
        sc = score.score_ranking(input_prompts["items"], input_prompts["ground_truth"], ans)           
    elif config.task_type == 'short_answer':
        ans = parse.parse_short_answer(turn.content)
        sc = -1 # score_short_answer needs to be written
    
    return ans, sc

def choose_submitting_agent(config, agt_indices):
    # choose an agent to state the team answer
    # input: agt_indices - list of agent indices to choose from    
    
    if config.randomize_final_submitter:
        agt_idx = random.choice(agt_indices)
    else:
        agt_idx = 0

    return agt_idx

def submit_team_answer(agt_idx, agents, input_prompts, config, final_round):
    
    submitting_agent = agents[agt_idx]

    if config.team_interdependence_type == "team":
        if final_round:
            content = input_prompts["team_prompt"]["final_answer"]
        else:
            content = input_prompts["team_prompt"]["round_answer"]
    elif config.team_interdependence_type.startswith("reciprocal"):
        if final_round:
            content = input_prompts["reciprocal_prompt"]["final_answer"]
        else:
            content = input_prompts["reciprocal_prompt"]["small_group_answer"]

    context_turn = Turn(speaker_id=-1, content=content)
    submitting_agent.trajectory.append(context_turn)
    turn = submitting_agent.act() # appends turn to current agent trajectory
    print(f"Agent {turn.speaker_id}: {turn.content}")

    return turn     

def human_agent(agents):

    # should human agent be listed as "system" for the speaker?
    
    prompt = input("Would you like to add a message to the discussion?")
    human_turn = Turn(speaker_id=-1, content=prompt)

    # Broadcast human agent message to all agents
    for agent in agents:
        agent.trajectory.append(human_turn)
                   
    
# ------------------------
# Team Interdependence Types   
# ------------------------

def pooled_task(agents, input_prompts, config):

    # returns a list of answers and scores - one pair for each agent
    # ONLY ONE ROUND
    
    answers = []
    scores = []
    
    for agent in agents:
        
        # each agent does task
        context_turn = Turn(speaker_id=-1, content=input_prompts["pooled_prompt"])
        agent.trajectory.append(context_turn)
        turn = agent.act()
        print(f"Agent {turn.speaker_id}: {turn.content}")

        # extract answer from LLM response (parse and score)
        ans, sc = parse_and_score(config, input_prompts, turn)
        answers.append(ans)
        scores.append(sc)

    '''
    # pool answers 
    print(answers)
    counts = Counter(answers)
    pooled_ans = counts.most_common(1)[0][0]
    print(f"Final pooled answer: {pooled_ans}") 
    return pooled_ans
    '''
    
    return answers, scores

def sequential_task(agents, input_prompts, config):

    # returns a list of answers and scores, one pair per round
    
    answers = []
    scores = []
    
    for r in range(config.max_rounds):
    
        for i, agent in enumerate(agents):
            
            # do task
            context_turn = Turn(speaker_id=-1, content=input_prompts["sequential_prompt"])
            agent.trajectory.append(context_turn)
            turn = agent.act()
            print(f"Agent {turn.speaker_id}: {turn.content}")
    
            # add to context of next agent or if last agent and not last round, add context back to first agent
            if i < len(agents)-1:
                agents[i+1].trajectory.append(turn)
            else: # last agent 
                if r < config.max_rounds-1: # not last round
                    agents[0].trajectory.append(turn)
                    
        # end of round r: save ans and score 
        print(f"\nRound {r+1} complete.\n") 
        ans, sc = parse_and_score(config, input_prompts, turn)
        answers.append(ans)
        scores.append(sc)
            
    return answers, scores    


def small_group_discussion(agents, input_prompts, config, sgr, st_agt, g):

    # One round of discussion
    # Each agent talks once
    
    if sgr == 0:
        prompt = input_prompts["reciprocal_prompt"]["small_group_first_round"]
    elif sgr == config.small_group_rounds-1:
        prompt = input_prompts["reciprocal_prompt"]["small_group_last_round"]
    else:
        prompt = input_prompts["reciprocal_prompt"]["small_group_mid_round"]

    # starting agent speaks then random order for other agents
    if config.randomize_speaking_order:
        g_ordered = [st_agt] + [agt_idx for agt_idx in random.sample(g, len(g)) if agt_idx != st_agt]
    else:
        g_ordered = [st_agt] + [agt_idx for agt_idx in g if agt_idx != st_agt]
    
    # loop over agents in small group
    for agt_idx in g_ordered:
        agent = agents[agt_idx]
        # do task
        context_turn = Turn(speaker_id=-1, content=prompt)
        agent.trajectory.append(context_turn)
        turn = agent.act()
        print(f"Agent {turn.speaker_id}: {turn.content}")

        # Share this turn with other agents in small group
        for other_agent_idx in g:
            if other_agent_idx != agt_idx:
                agents[other_agent_idx].trajectory.append(turn)
    

def reciprocal_chain_task(agents, input_prompts, config):

    # returns a list of answers and scores, one pair per round\

    answers = []
    scores = []

    # loop over chain rounds
    for r in range(config.max_rounds):

        # loop over small group discussion
        for i in range(len(config.small_groups)):

            g = config.small_groups[i]
            st_agt = config.small_group_reps[i]

            # loop over small group discussion rounds
            for sgr in range(config.small_group_rounds):
                small_group_discussion(agents, input_prompts, config, sgr, st_agt, g)
     
            # group representative gives information to next group or if last group and not last round, add context
            # back to first group
            rep_idx = config.small_group_reps[i]
            if (i == len(config.small_groups)-1) and (r == config.max_rounds-1):  #last small group and last round
                # get final answer
                turn = submit_team_answer(rep_idx, agents, input_prompts, config, final_round=True)
            else:                
                turn = submit_team_answer(rep_idx, agents, input_prompts, config, final_round=False)
                if i < len(config.small_groups)-1:
                    agents[config.small_group_reps[i+1]].trajectory.append(turn)
                else: # last small group
                    agents[config.small_group_reps[0]].trajectory.append(turn)
                        
        # end of round r: save ans and score 
        print(f"\nRound {r+1} complete.\n") 
        ans, sc = parse_and_score(config, input_prompts, turn)
        answers.append(ans)
        scores.append(sc)
                
    return answers, scores    

def reciprocal_subgroups_task(agents, input_prompts, config):

    # returns a list of answers and scores, one pair per round

    answers = []
    scores = []

    # loop over rounds
    for r in range(config.max_rounds):

        # loop over small group discussions
        for i in range(len(config.small_groups)):

            g = config.small_groups[i]
            st_agt = config.small_group_reps[i]

            # loop over small group discussion rounds
            for sgr in range(config.small_group_rounds):
                small_group_discussion(agents, input_prompts, config, sgr, st_agt, g)

            # SHARE GROUP RANKING?

        # Each small group rep shares their group ranking
        for rep_idx in config.small_group_reps:
            agent = agents[rep_idx]
            # do task
            context_turn = Turn(speaker_id=-1, content=input_prompts["reciprocal_prompt"]["small_group_answer"])
            agent.trajectory.append(context_turn)
            turn = agent.act()
            print(f"Agent {turn.speaker_id}: {turn.content}")

            # Share this turn with other reps 
            #for other_agent_idx in config.small_group_reps:
            #    if other_agent_idx != rep_idx:
            #        agents[other_agent_idx].trajectory.append(turn)
        
        # Reps discuss ranking over rounds
        for sgr in range(config.small_group_rounds):
            g = config.small_group_reps
            st_agt = g[0]  # default is first rep talks first
            small_group_discussion(agents, input_prompts, config, sgr, st_agt, g)

        # one rep shares rep ranking 
        # added to all rep trajectories for next round if not last round    
        sharing_rep = choose_submitting_agent(config, config.small_group_reps)
        if r == config.max_rounds-1:  #last round
            turn = submit_team_answer(sharing_rep, agents, input_prompts, config, final_round=True)
        else:
            turn = submit_team_answer(sharing_rep, agents, input_prompts, config, final_round=False)
            # Share this turn with all reps (who report consensus back to small groups)
            for other_rep_idx in config.small_group_reps:
                if other_rep_idx != sharing_rep:
                    agents[other_rep_idx].trajectory.append(turn)
                        
        # end of round r: save ans and score 
        print(f"\nRound {r+1} complete.\n") 
        ans, sc = parse_and_score(config, input_prompts, turn)
        answers.append(ans)
        scores.append(sc)
                
    return answers, scores    
    
    

def team_task(agents, input_prompts, config):

    # returns a list of answers and scores, one pair per round
    
    # NEED TO FIGURE OUT PROMPTS

    answers = []
    scores = []
    
    # loop over discussion rounds
    for r in range(config.max_rounds):

        if r != 0: # skip human agent in first round
            if config.human_interaction:
                human_agent(agents)
        
        if config.randomize_speaking_order:
            agt_order = random.sample(range(len(agents)), len(agents))
        else:
            agt_order = range(len(agents))
            
        if r == 0:
            prompt = input_prompts["team_prompt"]["first_round"]
        elif r == config.max_rounds-1:
            prompt = input_prompts["team_prompt"]["last_round"]
        else:
            prompt = input_prompts["team_prompt"]["mid_round"]
        
        # each agent talks once, all agents get others' responses
        for i in agt_order:
            agent = agents[i]
            context_turn = Turn(speaker_id=-1, content=prompt)
            agent.trajectory.append(context_turn)
            turn = agent.act() # appends turn to current agent trajectory
            print(f"Agent {turn.speaker_id}: {turn.content}")

            # Share this turn with all other agents
            for other_agent in agents:
                if other_agent.profile.agent_id != agent.profile.agent_id:
                    other_agent.trajectory.append(turn)

        # an agent gives the team answer after the round
        agt_idx = choose_submitting_agent(config, list(range(len(agents))))
        if r == config.max_rounds-1:  #last round
            turn = submit_team_answer(agt_idx, agents, input_prompts, config, final_round=True)
        else:
            turn = submit_team_answer(agt_idx, agents, input_prompts, config, final_round=False)
        
        # end of round r: save ans and score 
        print(f"\nRound {r+1} complete.\n")
        ans, sc = parse_and_score(config, input_prompts, turn)
        answers.append(ans)
        scores.append(sc)
                
    return answers, scores        
    
            