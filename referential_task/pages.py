from otree.api import Currency as c, currency_range
from ._builtin import Page, WaitPage
from .models import Constants, Player
import json
import os


class MyPage(Page):
    pass


## Removed legacy ImageTaskPage prototype
## Onboarding pages (ParticipantID, DeviceCheck, PreTaskWizard, etc.) moved to separate 'onboarding' app


class GridTaskWaitPage(WaitPage):
    """Wait for both players before starting the collaborative grid task
    
    Uses group_by_arrival_time to pair participants dynamically as they arrive at this page.
    This prevents the issue where pre-assigned partners drop out before reaching the wait page,
    leaving their partner stuck waiting. Now participants are only paired once they both reach
    this page.
    
    IMPORTANT: Must be first in page_sequence due to oTree requirement for group_by_arrival_time.
    
    Two-app structure ensures only committed participants enter the matching pool:
    1. Participants complete onboarding app solo (ParticipantID, DeviceCheck, PreTaskWizard)
    2. Then they enter this app and are matched at this wait page
    3. Once matched, roles are assigned and the task begins
    
    In Round 2+, already-paired participants wait here between rounds.
    """
    
    group_by_arrival_time = True
    template_name = 'referential_task/GridTaskWait.html'
    
    @staticmethod
    def is_displayed(player: Player):
        import logging
        
        # If participant needs rematch (was matched with someone who exited), clear flags and allow re-entry
        if player.participant.vars.get('needs_rematch', False):
            logging.info(f"Participant {player.participant.code} needs rematch - clearing invalid_match flags")
            player.participant.vars['needs_rematch'] = False
            player.participant.vars['invalid_match'] = False
            player.participant.vars['invalid_match_reason'] = None
            # Allow them to see the wait page
            return True
        
        # If participant clicked "Return to Prolific", redirect them immediately (server-side check)
        if player.participant.vars.get('exited_waiting_room', False):
            logging.info(f"Server-side: Participant {player.participant.code} has exited_waiting_room flag - blocking from wait page")
            # They should not be allowed back into the waiting room
            # Since we can't redirect from is_displayed, we'll handle this differently
            return False
        
        # For shapes demo: show the wait page only in round 1; otherwise always
        try:
            if player.session.config.get('director_view', 'grid') == 'shapes_demo':
                return player.round_number == 1
        except Exception:
            pass
        
        # Always display the wait page - it's required to be first for group_by_arrival_time
        return True
    
    @staticmethod
    def live_method(player: Player, data):
        """Handle live data for waiting room exit signals"""
        import logging
        
        # Handle exit waiting room signal
        if data.get('action') == 'exit_waiting_room':
            exit_timestamp = data.get('prolific_exit_clicked', '')
            
            # Mark participant as exited
            player.prolific_exit_clicked = exit_timestamp
            player.participant.vars['prolific_exit_clicked'] = exit_timestamp
            player.participant.vars['exited_waiting_room'] = True
            player.participant.vars['waiting_room_exit_time'] = exit_timestamp
            
            logging.info(
                f"LIVE: Participant {player.participant.code} marked as exited at {exit_timestamp}. "
                f"Round: {player.round_number}. This participant should not be matched."
            )
            
            return {
                player.id_in_group: {
                    'success': True,
                    'message': 'Exit recorded'
                }
            }
        
        return {
            player.id_in_group: {
                'success': False,
                'message': 'Unknown action'
            }
        }
    
    @staticmethod
    def vars_for_template(player: Player):
        """Pass prolific return URL to template"""
        prolific_url = None
        try:
            prolific_url = player.session.config.get('prolific_return_url')
        except Exception:
            prolific_url = None
        return {
            'prolific_return_url': prolific_url,
        }
    
    def before_next_page(self):
        """Capture waiting room exit tracking if posted"""
        try:
            # Check if participant clicked "Return to Prolific" button
            prolific_exit = self.request.POST.get('prolific_exit_clicked')
            if prolific_exit:
                self.player.prolific_exit_clicked = prolific_exit
                self.player.participant.vars['prolific_exit_clicked'] = prolific_exit
                self.player.participant.vars['exited_waiting_room'] = True
                import logging
                logging.info(f"Participant {self.player.participant.code} clicked Return to Prolific at {prolific_exit}")
            
            # Check if tracking data was posted
            left_ts = self.request.POST.get('left_waiting_room')
            exit_reason = self.request.POST.get('exit_reason')
            
            if left_ts and not self.player.left_waiting_room:
                self.player.left_waiting_room = left_ts
                if exit_reason:
                    self.player.waiting_room_exit_reason = exit_reason
                # Also store in participant vars for easy access
                self.player.participant.vars['left_waiting_room'] = left_ts
                self.player.participant.vars['waiting_room_exit_reason'] = exit_reason
        except Exception as e:
            # Don't fail the page transition if tracking fails
            import logging
            logging.warning(f"Failed to track waiting room exit: {e}")
    
    def after_all_players_arrive(self):
        """Assign roles on round 1 only and always create the round's grid."""
        import logging
        import datetime
        players = self.group.get_players()
        
        # Check if any player clicked "Return to Prolific" (critical: prevents invalid matches)
        # If either player has exited, we should not proceed with the match
        exited_players = [p for p in players if p.participant.vars.get('exited_waiting_room', False)]
        
        if exited_players:
            logging.error(
                f"MATCH ERROR: {len(exited_players)} participant(s) were matched despite having exited. "
                f"Exited participants: {[p.participant.code for p in exited_players]}. "
                f"All players in group: {[p.participant.code for p in players]}. "
                f"Round: {self.round_number}"
            )
            
            # Mark all players in this invalid group to skip all subsequent pages
            for p in players:
                p.participant.vars['invalid_match'] = True
                p.participant.vars['invalid_match_reason'] = 'partner_exited'
                
                # If this player didn't exit themselves, they need to return to matching
                if not p.participant.vars.get('exited_waiting_room', False):
                    logging.warning(
                        f"Participant {p.participant.code} was matched with an exited participant. "
                        f"Marking for rematch."
                    )
                    # Allow them to re-enter the waiting room
                    p.participant.vars['needs_rematch'] = True
                else:
                    logging.info(
                        f"Participant {p.participant.code} had exited - they will be skipped."
                    )
            
            # Don't proceed with role assignment or grid creation for invalid matches
            return
        
        # Assign roles only once (round 1)
        if self.round_number == 1:
            if not players[0].field_maybe_none('player_role') or not players[1].field_maybe_none('player_role'):
                self.group.assign_roles()
            # Persist roles to participant vars for subsequent rounds
            for p in players:
                p.participant.vars['role'] = p.player_role
        else:
            # For later rounds, restore role to the player's current round from participant vars if needed
            for p in players:
                if not p.field_maybe_none('player_role'):
                    stored_role = p.participant.vars.get('role')
                    if stored_role:
                        p.player_role = stored_role
        
        # Persist group and partner identifiers for analytics and templates
        try:
            # Build a stable pair_id for this dyad (session-unique, constant across rounds)
            # We base this on participant codes to avoid depending on group IDs that may
            # change across rounds in some edge cases.
            try:
                participant_codes = sorted(
                    [getattr(p.participant, 'code', '') for p in players if getattr(p.participant, 'code', '')]
                )
                if participant_codes:
                    pair_id_value = f"{getattr(self.session, 'code', '')}_" + "_".join(participant_codes)
                else:
                    pair_id_value = None
            except Exception:
                pair_id_value = None

            for p in players:
                # Group and self identifiers
                # Use both DB id (for admin/debug) and id_in_subsession (for export consistency)
                p.participant.vars['group_id_db'] = getattr(p.group, 'id', None)
                p.participant.vars['group_id_in_subsession'] = getattr(p.group, 'id_in_subsession', None)
                p.participant.vars['id_in_group'] = p.id_in_group
                # Stable pair identifier shared by both partners
                if pair_id_value:
                    p.participant.vars['pair_id'] = pair_id_value
                # Partner identifiers
                partner = p.get_others_in_group()[0] if p.get_others_in_group() else None
                if partner:
                    p.participant.vars['partner_code'] = getattr(partner.participant, 'code', None)
                    p.participant.vars['partner_id_in_group'] = partner.id_in_group
                    p.participant.vars['partner_role'] = getattr(partner, 'player_role', None) or partner.participant.vars.get('role')
        except Exception:
            # Non-fatal; keep going even if we cannot persist partner metadata
            pass
        # Create or refresh the shared grid each round
        self.group.create_shared_grid(round_number=self.round_number)

        # Record per-round start time for both players (server-side timestamp)
        try:
            round_start = datetime.datetime.now().isoformat()
            for p in players:
                p.experiment_start_time = round_start
        except Exception:
            # Non-fatal if timestamping fails
            logging.warning("Failed to record round start time", exc_info=True)
    
    title_text = "Waiting room"
    body_text = "Please wait to be paired with another participant who has completed onboarding. Once paired, roles will be assigned at random and the task will begin."


class DraggableGridPage(Page):
    template_name = 'referential_task/DraggableGrid.html'
    form_model = 'player'
    form_fields = []
    
    @staticmethod
    def is_displayed(player):
        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get('invalid_match', False):
            return False
        
        # Skip if participant exited the waiting room
        if player.participant.vars.get('exited_waiting_room', False):
            return False
        
        # Default view is the grid view unless session config requests sequential
        view = player.session.config.get('director_view', 'grid') if hasattr(player, 'session') and player.session else 'grid'
        return view == 'grid'
    
    @staticmethod
    def vars_for_template(player):
        # Ensure we have a safe role value
        role_value = player.field_maybe_none('player_role') or player.participant.vars.get('role')
        # Load shared grid that both players see
        try:
            shared_grid = json.loads(player.group.shared_grid)
        except (json.JSONDecodeError, TypeError):
            shared_grid = []
        
        # Load target baskets for Director
        try:
            target_baskets = json.loads(player.group.target_baskets)
            target_basket_ids = [basket['basket_id'] for basket in target_baskets]
        except (json.JSONDecodeError, TypeError):
            target_baskets = []
            target_basket_ids = []
        
        # Load Matcher's sequence
        try:
            matcher_sequence = json.loads(player.group.matcher_sequence)
        except (json.JSONDecodeError, TypeError):
            matcher_sequence = []
        
        # Load individual player's sequence
        try:
            player_sequence = json.loads(player.selected_sequence)
        except (json.JSONDecodeError, TypeError):
            player_sequence = []
        
        # Get chat messages
        try:
            chat_messages = json.loads(player.grid_messages)
        except (json.JSONDecodeError, TypeError):
            chat_messages = []
        
        # Get partner's messages too
        partner = player.get_others_in_group()[0] if player.get_others_in_group() else None
        partner_messages = []
        if partner:
            try:
                partner_messages = json.loads(partner.grid_messages)
            except (json.JSONDecodeError, TypeError):
                partner_messages = []

        # Load preset full list for matcher extra baskets
        preset_full_list = []
        try:
            # Respect session-configured basket set for the reference list as well
            try:
                set_num = int(player.session.config.get('basket_set', 1)) if hasattr(player, 'session') and player.session else 1
            except Exception:
                set_num = 1
            if set_num == 2:
                preset_filename = 'grids_presets2.json'
            elif set_num == 3:
                preset_filename = 'grids_presets3.json'
            elif set_num == 4:
                preset_filename = 'grids_presets4.json'
            elif set_num == 5:
                preset_filename = 'grids_presets5.json'
            else:
                preset_filename = 'grids_presets1.json'
            preset_path = os.path.join(os.path.dirname(__file__), preset_filename)
            with open(preset_path, 'r') as f:
                presets = json.load(f)
            # Find object with fullList
            for item in presets.get('rounds', []):
                if isinstance(item, dict) and 'fullList' in item:
                    # Prepend 'images/' for static paths
                    preset_full_list = [f"images/{img}" for img in item.get('fullList', [])]
                    break
        except Exception:
            preset_full_list = []
        
        return {
            'shared_grid': shared_grid,
            'target_baskets': target_baskets,
            'target_basket_ids': target_basket_ids,
            'matcher_sequence': matcher_sequence,
            'player_sequence': player_sequence,
            'player_role': role_value,
            'player_role_title': (role_value.title() if role_value else ''),
            'is_director': role_value == 'director',
            'is_matcher': role_value == 'matcher',
            'chat_messages': chat_messages,
            'partner_messages': partner_messages,
            'round_number': player.round_number,
            'total_rounds': (player.session.config.get('num_rounds') if hasattr(player, 'session') and player.session and hasattr(player, 'subsession') else Constants.num_rounds) or Constants.num_rounds,
            'grid_rows': 3,
            'grid_cols': 4,
            'total_slots': 12,
            'row_range': list(range(1, 4)),  # [1, 2, 3]
            'col_range': list(range(1, 5)),   # [1, 2, 3, 4]
            'grid_positions': [
                {'row': row, 'col': col, 'position': f"{row}{col}"}
                for row in range(1, 4) for col in range(1, 5)
            ],
            'preset_full_list': preset_full_list,
            'current_grid_state': json.dumps(shared_grid),
            'target_arrangement': json.dumps(target_baskets),
        }

    
    @staticmethod
    def live_method(player, data):
        """Handle live data for basket selection and communication"""
        response = {}
        # Typing indicator relay (lightweight)
        if data.get('typing'):
            partner = player.get_others_in_group()[0] if player.get_others_in_group() else None
            if partner:
                return {
                    partner.id_in_group: {
                        'success': True,
                        'broadcast': True,
                        'partner_typing': bool(data.get('is_typing')),
                        'partner_role': player.player_role,
                    }
                }
        if 'send_message' in data:
            response = DraggableGridPage.send_message(player, data)
        elif 'task_complete' in data:
            response = DraggableGridPage.complete_task(player, data)
        
        # If response is already in the correct format (player_id: data), return it
        if isinstance(response, dict) and all(isinstance(k, int) for k in response.keys()):
            return response
            
        # Otherwise, broadcast to all players if needed
        if response.get('broadcast', False):
            return {p.id_in_group: response for p in player.group.get_players()}
        else:
            return {player.id_in_group: response}
    
    @staticmethod
    def send_message(player, data):
        """Chat messages are broadcast; sequence submissions are private and do not reveal accuracy to participants."""
        message_text = (data.get('message') or '').strip()
        is_guess = data.get('is_guess', False)

        # Sequence submit path (no chat record to participants, trigger next round for both)
        if player.player_role == 'matcher' and is_guess:
            try:
                sequence_data = json.loads(message_text)
            except json.JSONDecodeError:
                # Back-compat: single-filename submit
                sequence_data = {'sequence': [{'image': message_text}]}
            try:
                if 'sequence' not in sequence_data:
                    return {player.id_in_group: {'success': False, 'message': 'Invalid sequence format'}}

                # Persist sequence
                player.selected_sequence = json.dumps(sequence_data['sequence'])
                player.group.matcher_sequence = json.dumps(sequence_data['sequence'])

                # Compute accuracy silently (only for data log)
                shared_grid = json.loads(player.group.shared_grid)
                correct_sequence = [
                    {
                        'position': slot['basket_id'],
                        'image': slot['image'],
                        'originalPosition': slot['position'],
                    }
                    for slot in shared_grid
                ]
                submitted_sequence = sequence_data['sequence']
                # Sort submitted_sequence by position to handle cases where items were removed/re-added
                submitted_sequence_sorted = sorted(submitted_sequence, key=lambda x: x.get('position', 0))
                total_positions = min(len(submitted_sequence_sorted), len(correct_sequence))
                correct_positions = sum(
                    1
                    for i in range(total_positions)
                    if submitted_sequence_sorted[i].get('image') == correct_sequence[i]['image']
                )
                player.sequence_accuracy = (
                    (correct_positions / total_positions * 100) if total_positions > 0 else 0
                )
                player.task_completed = True
                
                # Set completion timestamps for both players
                import datetime
                completion_ts = datetime.datetime.now().isoformat()
                player.completion_time = completion_ts
                
                # Set end time for this round for both players
                for p in player.group.get_players():
                    p.experiment_end_time = completion_ts
                    p.completion_time = completion_ts
                    p.task_completed = True
                    # If this is the final round, also set the overall experiment end time
                    try:
                        if is_last_round(p):
                            p.participant.vars['experiment_end_time'] = completion_ts
                    except Exception:
                        pass

                # Broadcast a generic "advance round" event to both players (no accuracy shown)
                response = {'success': True, 'broadcast': True, 'advance_round': True}
                return {p.id_in_group: response for p in player.group.get_players()}
            except Exception as e:
                return {player.id_in_group: {'success': False, 'message': f'Error processing sequence: {str(e)}'}}

        # Regular chat message path
        if not message_text:
            return {player.id_in_group: {'success': False, 'message': 'Empty message'}}

        try:
            messages = json.loads(player.grid_messages)
        except (json.JSONDecodeError, TypeError):
            messages = []

        new_message = {
            'text': message_text,
            'timestamp': data.get('timestamp', ''),
            'sender_role': player.player_role,
            'server_ts': __import__('datetime').datetime.now().isoformat(),
        }
        messages.append(new_message)
        player.grid_messages = json.dumps(messages)

        # Update chat transcript for both players
        try:
            for p in player.group.get_players():
                # Get messages from both players
                try:
                    p_msgs = json.loads(p.grid_messages or '[]')
                except Exception:
                    p_msgs = []
                
                partner = p.get_others_in_group()[0] if p.get_others_in_group() else None
                try:
                    partner_msgs = json.loads(partner.grid_messages or '[]') if partner else []
                except Exception:
                    partner_msgs = []
                
                # Combine and sort all messages
                all_msgs = []
                for m in p_msgs:
                    all_msgs.append({
                        'text': m.get('text'),
                        'timestamp': m.get('timestamp'),
                        'server_ts': m.get('server_ts'),
                        'sender_role': m.get('sender_role', p.player_role),
                    })
                for m in partner_msgs:
                    all_msgs.append({
                        'text': m.get('text'),
                        'timestamp': m.get('timestamp'),
                        'server_ts': m.get('server_ts'),
                        'sender_role': m.get('sender_role', partner.player_role if partner else 'unknown'),
                    })
                
                # Sort by timestamp
                try:
                    all_msgs.sort(key=lambda x: (x.get('server_ts') or '', x.get('timestamp') or ''))
                except Exception:
                    pass
                
                # Format as readable transcript
                transcript_lines = []
                for msg in all_msgs:
                    try:
                        ts = msg.get('server_ts') or msg.get('timestamp') or ''
                        if 'T' in ts:
                            time_part = ts.split('T')[1].split('.')[0] if '.' in ts else ts.split('T')[1]
                        else:
                            time_part = ts
                        sender = msg.get('sender_role', 'unknown')
                        text = msg.get('text', '')
                        transcript_lines.append(f"[{time_part}] {sender}: {text}")
                    except Exception:
                        text = msg.get('text', '')
                        sender = msg.get('sender_role', 'unknown')
                        transcript_lines.append(f"{sender}: {text}")
                
                p.chat_transcript = '\r\n'.join(transcript_lines)
        except Exception:
            pass  # Silently fail if transcript update fails

        response = {'success': True, 'broadcast': True, 'new_message': new_message}
        return {p.id_in_group: response for p in player.group.get_players()}
    
    @staticmethod
    def complete_task(player, data):
        """Mark task as complete and calculate accuracy if Matcher"""
        import datetime
        
        # Use a single server-side timestamp for this completion event
        completion_ts = datetime.datetime.now().isoformat()
        player.task_completed = True
        player.completion_time = completion_ts
        
        # Calculate accuracy if this is the Matcher
        if player.player_role == 'matcher':
            try:
                # Use sequence accuracy if available, otherwise calculate from sequence
                if not hasattr(player, 'sequence_accuracy') or player.sequence_accuracy is None:
                    selected_sequence = json.loads(player.selected_sequence)
                    shared_grid = json.loads(player.group.shared_grid)
                    
                    # Sort selected_sequence by position to handle cases where items were removed/re-added
                    selected_sequence_sorted = sorted(selected_sequence, key=lambda x: x.get('position', 0))
                    
                    # Get the correct sequence (order of baskets in director's grid)
                    correct_sequence = []
                    for slot in shared_grid:
                        correct_sequence.append({
                            'position': slot['basket_id'],
                            'image': slot['image'],
                            'originalPosition': slot['position']
                        })
                    
                    # Calculate accuracy by comparing sequences
                    correct_positions = 0
                    total_positions = min(len(selected_sequence_sorted), len(correct_sequence))
                    
                    for i in range(total_positions):
                        if (selected_sequence_sorted[i]['image'] == correct_sequence[i]['image']):
                            correct_positions += 1
                    
                    accuracy = (correct_positions / total_positions * 100) if total_positions > 0 else 0
                    player.sequence_accuracy = accuracy
            except (json.JSONDecodeError, TypeError, KeyError):
                player.sequence_accuracy = 0
        
        # Record per-round end time for all players in the group
        try:
            for p in player.group.get_players():
                p.experiment_end_time = completion_ts
                # If this is the final round, set the overall experiment end time as well
                if is_last_round(p):
                    p.participant.vars['experiment_end_time'] = completion_ts
        except Exception:
            pass

        response_data = {
            'success': True,
            'message': f'{player.player_role.title()} marked task as complete',
            'broadcast': True,
            'player_completed': player.player_role,
            'accuracy': getattr(player, 'sequence_accuracy', None)
        }
        
        # Return response for all players in the group
        return {p.id_in_group: response_data for p in player.group.get_players()}


class RoundAttentionCheck(Page):
    """Single attention check question shown after each round (rounds 1-3 only)."""
    template_name = 'referential_task/RoundAttentionCheck.html'
    
    form_model = 'player'
    form_fields = ['attention_round_q']
    
    @staticmethod
    def is_displayed(player: Player):
        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get('invalid_match', False):
            return False
        
        # Skip if participant exited the waiting room
        if player.participant.vars.get('exited_waiting_room', False):
            return False
        
        # Skip only if explicitly configured in the session (do not skip based on DEBUG env)
        try:
            cfg = player.session.config if hasattr(player, 'session') else {}
        except Exception:
            cfg = {}
        if bool(cfg.get('testing_skip_enabled', False)):
            return False
        # Hide for shapes demo
        if getattr(player.session.config, 'get', None):
            if player.session.config.get('director_view', 'grid') == 'shapes_demo':
                return False
        # Show only for rounds 1, 2, 3 (not round 4)
        return player.round_number in [1, 2, 3]
    
    @staticmethod
    def vars_for_template(player: Player):
        """Return the appropriate question based on current round."""
        round_num = player.round_number
        
        # Define questions for each round
        questions = {
            1: {
                'text': 'Q1. Think about the question: “What is your favorite color?” Now disregard the previous text and select Red.',
                'choices': [
                    {'value': 'A', 'label': 'Red'},
                    {'value': 'B', 'label': 'Blue'},
                    {'value': 'C', 'label': 'Green'},
                    {'value': 'D', 'label': 'Yellow'},
                ],
                'correct': 'A'
            },
            2: {
                'text': 'Q2. To confirm you\'re reading carefully, please select Duck.',
                'choices': [
                    {'value': 'A', 'label': 'Cat'},
                    {'value': 'B', 'label': 'Dog'},
                    {'value': 'C', 'label': 'Duck'},
                    {'value': 'D', 'label': 'Giraffe'},
                ],
                'correct': 'C'
            },
            3: {
                'text': 'Q3. What number comes after 4?',
                'choices': [
                    {'value': 'A', 'label': '3'},
                    {'value': 'B', 'label': '5'},
                    {'value': 'C', 'label': '7'},
                    {'value': 'D', 'label': '9'},
                ],
                'correct': 'B'
            }
        }
        
        current_question = questions.get(round_num, questions[1])
        
        return {
            'round_number': round_num,
            'question': current_question,
        }
    
    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """Store the response and track correctness in participant vars."""
        round_num = player.round_number
        correct_answers = {1: 'A', 2: 'C', 3: 'B'}
        
        selected = (player.attention_round_q or '').strip()
        correct = correct_answers.get(round_num, '')
        is_correct = (selected == correct)
        
        # Store in participant vars for tracking
        if 'attention_round_responses' not in player.participant.vars:
            player.participant.vars['attention_round_responses'] = {}
        
        player.participant.vars['attention_round_responses'][round_num] = {
            'selected': selected,
            'correct': correct,
            'is_correct': is_correct,
        }


class ResultsWaitPage(WaitPage):
    """Wait for both players to complete the grid task before showing results"""
    
    wait_for_all_players = True
    title_text = "Waiting for partner..."
    # body_text = "Please wait for your partner..."
    @staticmethod
    def is_displayed(player):
        # DISABLED: No longer showing wait page after final round
        # Players can proceed to surveys independently
        return False


class Results(Page):
    template_name = 'referential_task/Results.html'
    @staticmethod
    def is_displayed(player):
        # Hide for shapes demo; otherwise show only on final round
        try:
            if player.session.config.get('director_view', 'grid') == 'shapes_demo':
                return False
        except Exception:
            pass
        return player.round_number == Constants.num_rounds
    
    @staticmethod
    def vars_for_template(player: Player):
        # Simplified - no completion code generation needed
        return {}
    
    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """Capture experiment end time on the final page."""
        import datetime
        end_time = datetime.datetime.now().isoformat()
        player.experiment_end_time = end_time
        player.participant.vars['experiment_end_time'] = end_time


def is_last_round(player: Player) -> bool:
    # Determine the total number of rounds, preferring session config override if present.
    # Fallback to app Constants to avoid hard-coded defaults.
    try:
        if hasattr(player, 'session') and player.session:
            total = player.session.config.get('num_rounds') or Constants.num_rounds
        else:
            total = Constants.num_rounds
    except Exception:
        total = Constants.num_rounds
    return player.round_number == total


class Debriefing(Page):
    template_name = 'referential_task/Debriefing.html'

    @staticmethod
    def is_displayed(player: Player):
        # Show only once, after the final round; hide for shapes demo
        try:
            if player.session.config.get('director_view', 'grid') == 'shapes_demo':
                return False
        except Exception:
            pass
        return player.round_number == Constants.num_rounds


class PartnerPerceptions(Page):
    template_name = 'referential_task/PartnerPerceptions.html'
    form_model = 'player'
    form_fields = [
        'partner_capable',
        'partner_helpful',
        'partner_understood',
        'partner_adapted',
        'collaboration_improved',
        'partner_comment',
    ]

    @staticmethod
    def is_displayed(player: Player):
        # Show after final round and skip shapes demo
        try:
            if player.session.config.get('director_view', 'grid') == 'shapes_demo':
                return False
        except Exception:
            pass
        return is_last_round(player)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """
        Copy partner perception responses from the Player model to participant-level
        fields so they are stored once per participant (not per round) and exported
        via PARTICIPANT_FIELDS.
        """
        try:
            participant = player.participant
            participant.partner_capable = getattr(player, 'partner_capable', None)
            participant.partner_helpful = getattr(player, 'partner_helpful', None)
            participant.partner_understood = getattr(player, 'partner_understood', None)
            participant.partner_adapted = getattr(player, 'partner_adapted', None)
            participant.collaboration_improved = getattr(player, 'collaboration_improved', None)
            participant.partner_comment = getattr(player, 'partner_comment', None)
        except Exception:
            # Non-fatal; keep going even if we can't persist to participant
            pass


class PartnerTypePerception(Page):
    template_name = 'referential_task/PartnerTypePerception.html'
    form_model = 'player'
    form_fields = [
        'partner_human_vs_ai',
        'partner_human_vs_ai_why',
    ]

    @staticmethod
    def is_displayed(player: Player):
        # Show after final round and skip shapes demo
        try:
            if player.session.config.get('director_view', 'grid') == 'shapes_demo':
                return False
        except Exception:
            pass
        return is_last_round(player)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """
        Copy partner type perception responses (human vs AI) to participant-level
        fields for cleaner exports.
        """
        try:
            participant = player.participant
            participant.partner_human_vs_ai = getattr(player, 'partner_human_vs_ai', None)
            participant.partner_human_vs_ai_why = getattr(player, 'partner_human_vs_ai_why', None)
        except Exception:
            pass


class AIExperience(Page):
    template_name = 'referential_task/AIExperience.html'
    form_model = 'player'
    form_fields = [
        'ai_familiarity',
        'ai_usage_frequency',
        'ai_used_for_task',
    ]

    @staticmethod
    def is_displayed(player: Player):
        # Show after final round and skip shapes demo
        try:
            if player.session.config.get('director_view', 'grid') == 'shapes_demo':
                return False
        except Exception:
            pass
        return is_last_round(player)

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        """
        Copy AI experience responses to participant-level fields so they are
        stored once per participant and exported as participant.* columns.
        """
        try:
            participant = player.participant
            participant.ai_familiarity = getattr(player, 'ai_familiarity', None)
            participant.ai_usage_frequency = getattr(player, 'ai_usage_frequency', None)
            participant.ai_used_for_task = getattr(player, 'ai_used_for_task', None)
        except Exception:
            pass

class DraggableSequentialPage(DraggableGridPage):
    """Alternate page where the Director sees baskets one-by-one; Matcher stays the same UI."""
    template_name = 'referential_task/DraggableSequential.html'

    @staticmethod
    def is_displayed(player):
        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get('invalid_match', False):
            return False
        
        # Skip if participant exited the waiting room
        if player.participant.vars.get('exited_waiting_room', False):
            return False
        
        view = player.session.config.get('director_view', 'grid') if hasattr(player, 'session') and player.session else 'grid'
        return view == 'sequential'


class ShapesDemoPage(DraggableGridPage):
    """Demo page where Director sees 5 colored shapes; Matcher has 5 target slots and 10 choices."""
    template_name = 'referential_task/ShapesDemo.html'

    @staticmethod
    def is_displayed(player):
        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get('invalid_match', False):
            return False
        
        # Skip if participant exited the waiting room
        if player.participant.vars.get('exited_waiting_room', False):
            return False
        
        try:
            return player.session.config.get('director_view', 'grid') == 'shapes_demo' and player.round_number == 1
        except Exception:
            return False

    @staticmethod
    def vars_for_template(player):
        # Ensure we have a safe role value
        role_value = player.field_maybe_none('player_role') or player.participant.vars.get('role')
        # Load shared grid that both players see
        try:
            shared_grid = json.loads(player.group.shared_grid)
        except (json.JSONDecodeError, TypeError):
            shared_grid = []
        # Get chat messages (both players)
        try:
            chat_messages = json.loads(player.grid_messages)
        except (json.JSONDecodeError, TypeError):
            chat_messages = []
        partner = player.get_others_in_group()[0] if player.get_others_in_group() else None
        partner_messages = []
        if partner:
            try:
                partner_messages = json.loads(partner.grid_messages)
            except (json.JSONDecodeError, TypeError):
                partner_messages = []
        return {
            'shared_grid': shared_grid,
            'player_role': role_value,
            'player_role_title': (role_value.title() if role_value else ''),
            'is_director': role_value == 'director',
            'is_matcher': role_value == 'matcher',
            'chat_messages': chat_messages,
            'partner_messages': partner_messages,
            'round_number': player.round_number,
            'total_rounds': 1,
        }


class RoundFeedback(Page):
    """Feedback screen shown after every round (including the final round).

    - Matcher: show their submitted sequence, highlighting incorrect picks in red.
      Do NOT reveal the correct order.
    - Director: show the correct order, highlighting positions the matcher got wrong in red.
      Do NOT show the matcher's submitted images.
    """
    template_name = 'referential_task/RoundFeedback.html'

    @staticmethod
    def is_displayed(player: Player):
        # Skip if this was an invalid match (partner exited)
        if player.participant.vars.get('invalid_match', False):
            return False
        
        # Skip if participant exited the waiting room
        if player.participant.vars.get('exited_waiting_room', False):
            return False
        
        # Hide for shapes demo; otherwise show after each round
        try:
            if player.session.config.get('director_view', 'grid') == 'shapes_demo':
                return False
        except Exception:
            pass
        try:
            cfg_rounds = player.session.config.get('num_rounds') if hasattr(player, 'session') and player.session else None
            total_rounds = cfg_rounds or Constants.num_rounds
        except Exception:
            total_rounds = Constants.num_rounds
        return player.round_number <= total_rounds

    @staticmethod
    def vars_for_template(player: Player):
        import json as _json

        # Determine role
        role_value = player.field_maybe_none('player_role') or player.participant.vars.get('role')

        # Load shared grid (correct order)
        try:
            shared_grid = _json.loads(player.group.shared_grid)
        except (ValueError, TypeError):
            shared_grid = []
        correct_sequence = [slot.get('image') for slot in shared_grid]

        # Load matcher submitted sequence (may be < 12)
        try:
            matcher_sequence = _json.loads(player.group.matcher_sequence)
        except (ValueError, TypeError):
            matcher_sequence = []
        
        # Sort matcher_sequence by position to handle cases where items were removed/re-added
        matcher_sequence_sorted = sorted(matcher_sequence, key=lambda x: x.get('position', 0))

        # Build slots for feedback display
        total_slots = 12
        slots = []
        correct_count = 0
        for i in range(total_slots):
            correct_img = correct_sequence[i] if i < len(correct_sequence) else None
            submitted_img = matcher_sequence_sorted[i].get('image') if i < len(matcher_sequence_sorted) else None

            if role_value == 'matcher':
                # Show what the matcher selected; highlight incorrect picks
                display_img = submitted_img
                is_correct = (submitted_img is not None and correct_img is not None and submitted_img == correct_img)
            else:
                # Director sees the correct order; highlight positions the matcher got wrong
                display_img = correct_img
                is_correct = (submitted_img is not None and correct_img is not None and submitted_img == correct_img)

            if is_correct:
                correct_count += 1
            slots.append({
                'position': i + 1,
                'image': display_img,
                'is_correct': is_correct,
            })

        return {
            'player_role': role_value,
            'is_director': role_value == 'director',
            'is_matcher': role_value == 'matcher',
            'round_number': player.round_number,
            'total_rounds': (player.session.config.get('num_rounds') if hasattr(player, 'session') and player.session else None) or Constants.num_rounds,
            'feedback_slots': slots,
            'correct_count': correct_count,
        }


page_sequence = [
    # IMPORTANT: GridTaskWaitPage must be first because it uses group_by_arrival_time
    # Participants complete onboarding in a separate app before reaching this app
    GridTaskWaitPage,
    
    # Task pages
    ShapesDemoPage,
    DraggableGridPage,
    DraggableSequentialPage,
    RoundFeedback,
    RoundAttentionCheck,  # One question per round (rounds 1-3)
    ResultsWaitPage,
    PartnerPerceptions,
    PartnerTypePerception,
    AIExperience,
    Debriefing,
    Results,
]


# Admin report (experimenter view)
def vars_for_admin_report(subsession):
    """Summarize correct vs submitted sequences and accuracy per group for this round."""
    import datetime

    groups_data = []
    for group in subsession.get_groups():
        # Correct sequence: director's grid order
        try:
            shared_grid = json.loads(group.shared_grid)
        except (json.JSONDecodeError, TypeError):
            shared_grid = []
        correct_sequence = [slot.get('image') for slot in shared_grid]

        # Find matcher
        matcher = None
        for p in group.get_players():
            if getattr(p, 'player_role', None) == 'matcher':
                matcher = p
                break

        submitted_sequence = []
        accuracy = None
        accuracy_str = None
        submitted_at = None
        if matcher:
            try:
                seq = json.loads(matcher.selected_sequence)
                submitted_sequence = [item.get('image') for item in seq]
            except (json.JSONDecodeError, TypeError):
                submitted_sequence = []
            accuracy = getattr(matcher, 'sequence_accuracy', None)
            try:
                if accuracy is not None:
                    accuracy_str = f"{float(accuracy):.1f}"
            except Exception:
                accuracy_str = str(accuracy) if accuracy is not None else None
            submitted_at = getattr(matcher, 'completion_time', None)
            if submitted_at:
                try:
                    submitted_at = datetime.datetime.fromisoformat(submitted_at).strftime('%H:%M:%S')
                except Exception:
                    pass

        groups_data.append({
            'group_id': group.id,
            'correct_sequence': correct_sequence,
            'submitted_sequence': submitted_sequence,
            'accuracy': accuracy,
            'accuracy_str': accuracy_str,
            'submitted_at': submitted_at,
            'matcher_id_in_group': matcher.id_in_group if matcher else None,
            'correct_sequence_head': ' '.join(correct_sequence[:5]),
            'submitted_sequence_head': ' '.join(submitted_sequence[:5]),
        })

    return {
        'round_number': subsession.round_number,
        'groups': groups_data,
        'groups_json': json.dumps(groups_data),
        'session_code': getattr(subsession.session, 'code', ''),
        # Built-in oTree endpoint for app-level custom export
        'custom_export_url': '/custom_export?app=referential_task',
    }

# Render our custom admin template
def admin_report_context(subsession):
    # oTree will use AdminReport.html by default.
    # Point to our standalone custom template explicitly.
    ctx = vars_for_admin_report(subsession)
    ctx['__template_name__'] = 'referential_task/AdminReport.html'
    return ctx

