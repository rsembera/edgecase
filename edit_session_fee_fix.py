# FIX FOR edit_session ROUTE - Replace the fee breakdown comparison section

# Starting around line 867, replace these lines:

            # Fee breakdown
            if old_session.get('base_fee') != session_data.get('base_fee'):
                changes.append(f"Base Fee: ${old_session.get('base_fee', 0):.2f} → ${session_data.get('base_fee', 0):.2f}")
            
            if old_session.get('tax_rate') != session_data.get('tax_rate'):
                changes.append(f"Tax Rate: {old_session.get('tax_rate', 0):.2f}% → {session_data.get('tax_rate', 0):.2f}%")
            
            if old_session.get('fee') != session_data.get('fee'):
                changes.append(f"Total Fee: ${old_session.get('fee', 0):.2f} → ${session_data.get('fee', 0):.2f}")

# WITH:

            # Fee breakdown (handle None values explicitly)
            if old_session.get('base_fee') != session_data.get('base_fee'):
                old_base = old_session.get('base_fee')
                new_base = session_data.get('base_fee')
                old_str = f"${old_base:.2f}" if old_base is not None else "None"
                new_str = f"${new_base:.2f}" if new_base is not None else "None"
                changes.append(f"Base Fee: {old_str} → {new_str}")
            
            if old_session.get('tax_rate') != session_data.get('tax_rate'):
                old_tax = old_session.get('tax_rate')
                new_tax = session_data.get('tax_rate')
                old_str = f"{old_tax:.2f}%" if old_tax is not None else "None"
                new_str = f"{new_tax:.2f}%" if new_tax is not None else "None"
                changes.append(f"Tax Rate: {old_str} → {new_str}")
            
            if old_session.get('fee') != session_data.get('fee'):
                old_fee = old_session.get('fee')
                new_fee = session_data.get('fee')
                old_str = f"${old_fee:.2f}" if old_fee is not None else "None"
                new_str = f"${new_fee:.2f}" if new_fee is not None else "None"
                changes.append(f"Total Fee: {old_str} → {new_str}")
