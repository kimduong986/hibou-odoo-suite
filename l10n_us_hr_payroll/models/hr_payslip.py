# Part of Hibou Suite Professional. See LICENSE_PROFESSIONAL file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import UserError

from .federal.fed_940 import er_us_940_futa
from .federal.fed_941 import ee_us_941_fica_ss, \
                             ee_us_941_fica_m, \
                             ee_us_941_fica_m_add,\
                             er_us_941_fica_ss, \
                             er_us_941_fica_m, \
                             ee_us_941_fit
from .state.general import general_state_unemployment, \
                           general_state_income_withholding, \
                           is_us_state
from .state.al_alabama import al_alabama_state_income_withholding
from .state.ar_arkansas import ar_arkansas_state_income_withholding
from .state.az_arizona import az_arizona_state_income_withholding
from .state.ca_california import ca_california_state_income_withholding
from .state.ct_connecticut import ct_connecticut_state_income_withholding
from .state.ga_georgia import ga_georgia_state_income_withholding
from .state.il_illinois import il_illinois_state_income_withholding
from .state.mi_michigan import mi_michigan_state_income_withholding
from .state.mn_minnesota import mn_minnesota_state_income_withholding
from .state.mo_missouri import mo_missouri_state_income_withholding
from .state.ms_mississippi import ms_mississippi_state_income_withholding
from .state.mt_montana import mt_montana_state_income_withholding
from .state.nc_northcarolina import nc_northcarolina_state_income_withholding
from .state.nj_newjersey import nj_newjersey_state_income_withholding
from .state.oh_ohio import oh_ohio_state_income_withholding
from .state.va_virginia import va_virginia_state_income_withholding
from .state.wa_washington import wa_washington_fml_er, \
                                 wa_washington_fml_ee


class HRPayslip(models.Model):
    _inherit = 'hr.payslip'

    # From IRS Publication 15-T or logically (annually, bi-monthly)
    PAY_PERIODS_IN_YEAR = {
            'annually':        1,
            'semi-annually':   2,
            'quarterly':       4,
            'bi-monthly':      6,
            'monthly':        12,
            'semi-monthly':   24,
            'bi-weekly':      26,
            'weekly':         52,
            'daily':         260,
        }

    def _get_base_local_dict(self):
        # back port for US Payroll
        #res = super()._get_base_local_dict()
        return {
            'er_us_940_futa': er_us_940_futa,
            'ee_us_941_fica_ss': ee_us_941_fica_ss,
            'ee_us_941_fica_m': ee_us_941_fica_m,
            'ee_us_941_fica_m_add': ee_us_941_fica_m_add,
            'er_us_941_fica_ss': er_us_941_fica_ss,
            'er_us_941_fica_m': er_us_941_fica_m,
            'ee_us_941_fit': ee_us_941_fit,
            'general_state_unemployment': general_state_unemployment,
            'general_state_income_withholding': general_state_income_withholding,
            'is_us_state': is_us_state,
            'al_alabama_state_income_withholding': al_alabama_state_income_withholding,
            'ar_arkansas_state_income_withholding': ar_arkansas_state_income_withholding,
            'az_arizona_state_income_withholding': az_arizona_state_income_withholding,
            'ca_california_state_income_withholding': ca_california_state_income_withholding,
            'ct_connecticut_state_income_withholding': ct_connecticut_state_income_withholding,
            'ga_georgia_state_income_withholding': ga_georgia_state_income_withholding,
            'il_illinois_state_income_withholding': il_illinois_state_income_withholding,
            'mi_michigan_state_income_withholding': mi_michigan_state_income_withholding,
            'mn_minnesota_state_income_withholding': mn_minnesota_state_income_withholding,
            'mo_missouri_state_income_withholding': mo_missouri_state_income_withholding,
            'ms_mississippi_state_income_withholding': ms_mississippi_state_income_withholding,
            'mt_montana_state_income_withholding': mt_montana_state_income_withholding,
            'nc_northcarolina_state_income_withholding': nc_northcarolina_state_income_withholding,
            'nj_newjersey_state_income_withholding': nj_newjersey_state_income_withholding,
            'oh_ohio_state_income_withholding': oh_ohio_state_income_withholding,
            'va_virginia_state_income_withholding': va_virginia_state_income_withholding,
            'wa_washington_fml_er': wa_washington_fml_er,
            'wa_washington_fml_ee': wa_washington_fml_ee,
        }

    def get_year(self):
        # Helper method to get the year (normalized between Odoo Versions)
        return self.date_to.year

    def get_pay_periods_in_year(self):
        return self.PAY_PERIODS_IN_YEAR.get(self.contract_id.schedule_pay, 0)

    @api.model
    def _get_payslip_lines(self, contract_ids, payslip_id):
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            localdict['categories'].dict[category.code] = category.code in localdict['categories'].dict and localdict['categories'].dict[category.code] + amount or amount
            return localdict

        class BrowsableObject(object):
            def __init__(self, employee_id, dict, env):
                self.employee_id = employee_id
                self.dict = dict
                self.env = env

            def __getattr__(self, attr):
                return attr in self.dict and self.dict.__getitem__(attr) or 0.0

        class InputLine(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""
                    SELECT sum(amount) as sum
                    FROM hr_payslip as hp, hr_payslip_input as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()[0] or 0.0

        class WorkedDays(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""
            def _sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""
                    SELECT sum(number_of_days) as number_of_days, sum(number_of_hours) as number_of_hours
                    FROM hr_payslip as hp, hr_payslip_worked_days as pi
                    WHERE hp.employee_id = %s AND hp.state = 'done'
                    AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pi.payslip_id AND pi.code = %s""",
                    (self.employee_id, from_date, to_date, code))
                return self.env.cr.fetchone()

            def sum(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[0] or 0.0

            def sum_hours(self, code, from_date, to_date=None):
                res = self._sum(code, from_date, to_date)
                return res and res[1] or 0.0

        class Payslips(BrowsableObject):
            """a class that will be used into the python code, mainly for usability purposes"""

            def sum(self, code, from_date, to_date=None):
                if to_date is None:
                    to_date = fields.Date.today()
                self.env.cr.execute("""SELECT sum(case when hp.credit_note = False then (pl.total) else (-pl.total) end)
                            FROM hr_payslip as hp, hr_payslip_line as pl
                            WHERE hp.employee_id = %s AND hp.state = 'done'
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id AND pl.code = %s""",
                            (self.employee_id, from_date, to_date, code))
                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

            def sum_category(self, code, from_date, to_date=None):
                # Hibou Backport
                if to_date is None:
                    to_date = fields.Date.today()

                self.env.cr.execute("""SELECT sum(case when hp.credit_note is not True then (pl.total) else (-pl.total) end)
                            FROM hr_payslip as hp, hr_payslip_line as pl, hr_salary_rule_category as rc
                            WHERE hp.employee_id = %s AND hp.state = 'done'
                            AND hp.date_from >= %s AND hp.date_to <= %s AND hp.id = pl.slip_id
                            AND rc.id = pl.category_id AND rc.code = %s""",
                                    (self.employee_id, from_date, to_date, code))
                res = self.env.cr.fetchone()
                return res and res[0] or 0.0

        #we keep a dict with the result because a value can be overwritten by another rule with the same code
        result_dict = {}
        rules_dict = {}
        worked_days_dict = {}
        inputs_dict = {}
        blacklist = []
        payslip = self.env['hr.payslip'].browse(payslip_id)
        for worked_days_line in payslip.worked_days_line_ids:
            worked_days_dict[worked_days_line.code] = worked_days_line
        for input_line in payslip.input_line_ids:
            inputs_dict[input_line.code] = input_line

        categories = BrowsableObject(payslip.employee_id.id, {}, self.env)
        inputs = InputLine(payslip.employee_id.id, inputs_dict, self.env)
        worked_days = WorkedDays(payslip.employee_id.id, worked_days_dict, self.env)
        payslips = Payslips(payslip.employee_id.id, payslip, self.env)
        rules = BrowsableObject(payslip.employee_id.id, rules_dict, self.env)

        baselocaldict = {'categories': categories, 'rules': rules, 'payslip': payslips, 'worked_days': worked_days, 'inputs': inputs}

        # Hibou Backport
        baselocaldict.update(self._get_base_local_dict())

        #get the ids of the structures on the contracts and their parent id as well
        contracts = self.env['hr.contract'].browse(contract_ids)
        if len(contracts) == 1 and payslip.struct_id:
            structure_ids = list(set(payslip.struct_id._get_parent_structure().ids))
        else:
            structure_ids = contracts.get_all_structures()
        #get the rules of the structure and thier children
        rule_ids = self.env['hr.payroll.structure'].browse(structure_ids).get_all_rules()
        #run the rules by sequence
        sorted_rule_ids = [id for id, sequence in sorted(rule_ids, key=lambda x:x[1])]
        sorted_rules = self.env['hr.salary.rule'].browse(sorted_rule_ids)

        for contract in contracts:
            employee = contract.employee_id
            localdict = dict(baselocaldict, employee=employee, contract=contract)
            for rule in sorted_rules:
                key = rule.code + '-' + str(contract.id)
                localdict['result'] = None
                localdict['result_qty'] = 1.0
                localdict['result_rate'] = 100
                #check if the rule can be applied
                if rule._satisfy_condition(localdict) and rule.id not in blacklist:
                    #compute the amount of the rule
                    amount, qty, rate = rule._compute_rule(localdict)
                    #check if there is already a rule computed with that code
                    previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                    #set/overwrite the amount computed for this rule in the localdict
                    tot_rule = amount * qty * rate / 100.0
                    localdict[rule.code] = tot_rule
                    rules_dict[rule.code] = rule
                    #sum the amount for its salary category
                    localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount)
                    #create/overwrite the rule in the temporary results
                    result_dict[key] = {
                        'salary_rule_id': rule.id,
                        'contract_id': contract.id,
                        'name': rule.name,
                        'code': rule.code,
                        'category_id': rule.category_id.id,
                        'sequence': rule.sequence,
                        'appears_on_payslip': rule.appears_on_payslip,
                        'condition_select': rule.condition_select,
                        'condition_python': rule.condition_python,
                        'condition_range': rule.condition_range,
                        'condition_range_min': rule.condition_range_min,
                        'condition_range_max': rule.condition_range_max,
                        'amount_select': rule.amount_select,
                        'amount_fix': rule.amount_fix,
                        'amount_python_compute': rule.amount_python_compute,
                        'amount_percentage': rule.amount_percentage,
                        'amount_percentage_base': rule.amount_percentage_base,
                        'register_id': rule.register_id.id,
                        'amount': amount,
                        'employee_id': contract.employee_id.id,
                        'quantity': qty,
                        'rate': rate,
                    }
                else:
                    #blacklist this rule and its children
                    blacklist += [id for id, seq in rule._recursive_search_of_rules()]

        return list(result_dict.values())
