%rebase layout globals(), css=['eltgroup/css/group-detail.css'], title='Group overview', menu_part=''

<div class="row-fluid">
	<h3 class="no-topmargin">hostgroup_name</h3>
</div>

<div class="row-fluid">
	<div class="accordion" id="fitted-accordion">
		<div class="fitted-box overall-summary accordion-group">
			<div class="accordion-heading">
				<a class="accordion-toggle" data-toggle="collapse" data-parent="#fitted-accordion" href="#collapseOne">
					Overview (alias)
				</a>
			</div>
			<div id="collapseOne" class="accordion-body collapse in">
				<div class="row-fluid fitted-bar ">
					<div class="progress">
						<div class="bar bar-success quickinfo" data-original-title='35% Up' style="width: 35%;"></div>
						<div class="bar bar-info quickinfo" data-original-title='20% Unreachable' style="width: 20%;"></div>
						<div class="bar bar-danger quickinfo" data-original-title='10% Down' style="width: 10%;"></div>
						<div class="bar bar-warning quickinfo" data-original-title='35% Warning' style="width: 35%;"></div>
					</div>
				</div>
				<div class="accordion-inner">
					<ul>
						<li class="span3"><span class="num">35</span> Up</li>
						<li class="span3"><span class="num">10</span> Down</li>
						<li class="span3"><span class="num">23</span> Unreachable</li>
						<li class="span3"><span class="num">10</span> Pending</li>
					</ul>
				</div>
			</div>
		</div>
    </div>
    
	<div>
		<div class="clearfix">
			<table class="table table-hover">
				<tbody>
					<tr>
						<th><em>Status</em></th>
						<th>Host</th>
						<th><em>Status</em></th>
						<th>Service</th>
						<th>Last Check</th>
						<th>Duration</th>
						<th>Attempt</th>
						<th>Status Information</th>
					</tr>
					<tr>
						<td ><em>UP</em></td>
						<td>
							<span><a href="#">localost</a></span>
						</td>
						<td><em>OK</em></td>

						<td style="white-space: normal">
							<span>Ping</span>
						</td>
						<td>2012-07-30 22:53:03</td>
						<td>352d 23h 56m 56s</td>
						<td>1/3</td>
						<td>OK - localhost</td>	
					</tr>

					<tr>
						<td></td>
						<td>&nbsp;</td>
						<td><em>OK</em></td>
						<td>
							<span> <a href="#">Test</a> </span>
						</td>
						<td>2012-07-30 22:53:03</td>
						<td>89d 17h 15m 59s</td>
						<td>1/1</td>
						<td>Service not intended for active checks</td>
					</tr>

					<tr>
						<td></td>
						<td>&nbsp;</td>
						<td><em>OK</em></td>
						<td>
							<span> <a href="#">Test</a> </span>
						</td>
						<td>2012-07-30 22:53:03</td>
						<td>89d 17h 15m 59s</td>
						<td>1/1</td>
						<td>Service not intended for active checks</td>
						<td></td>
					</tr>
					<tr>
						<td ><em>UP</em></td>
						<td>
							<span><a href="#">orca</a></span>
						</td>
						<td><em>OK</em></td>

						<td style="white-space: normal">
							<span>Ping</span>
						</td>
						<td>2012-07-30 22:53:03</td>
						<td>352d 23h 56m 56s</td>
						<td>1/3</td>
						<td>OK - localhost</td>
					</tr>

					<tr>
						<td></td>
						<td>&nbsp;</td>
						<td><em>OK</em></td>
						<td>
							<span> <a href="#">Test</a> </span>
						</td>
						<td>2012-07-30 22:53:03</td>
						<td>89d 17h 15m 59s</td>
						<td>1/1</td>
						<td>Service not intended for active checks</td>
					</tr>

					<tr>
						<td></td>
						<td>&nbsp;</td>
						<td><em>OK</em></td>
						<td>
							<span> <a href="#">Test</a> </span>
						</td>
						<td>2012-07-30 22:53:03</td>
						<td>89d 17h 15m 59s</td>
						<td>1/1</td>
						<td>Service not intended for active checks</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>

	<div class="pull-right">
		<div class="pagination">
			<ul>
				<li><a href="#">Prev</a></li>
				<li><a href="#">1</a></li>
				<li><a href="#">2</a></li>
				<li><a href="#">3</a></li>
				<li><a href="#">4</a></li>
				<li><a href="#">Next</a></li>
			</ul>
		</div>
	</div> 
</div>