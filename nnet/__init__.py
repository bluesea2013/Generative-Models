import tensorflow as tf 
import numpy as np
import time
import os
import datetime

import modules as model
from options import Options
from utils import Dataset

class GAN(object):

	def __init__(self, opts, is_training=False):
		self.h = opts.image_size_h
		self.w = opts.image_size_w
		self.c = opts.channels
		self.opts = opts
		self.images = tf.placeholder(tf.float32, [None, self.h, self.w, self.c], "images")
		if self.opts.use_labels:
			self.labels = tf.placeholder(tf.float32, [None, self.opts.label_len], "labels")
		self.code = tf.placeholder(tf.float32, [None, self.opts.code_len], "code")
		self.D_lr = tf.placeholder(tf.float32, [], "D_learning_rate")
		self.G_lr = tf.placeholder(tf.float32, [], "G_learning_rate")
		self.is_training = self.opts.train
		self.generated_imgs = self.Generator(self.code)
		self.true_logit = self.Discriminator(self.images, reuse=False)
		self.fake_logit = self.Discriminator(self.generated_imgs, reuse=True)
		self.d_loss, self.g_loss = self.loss()

		# self.plot_gradients_summary("Discriminator")
		# self.plot_gradients_summary("Generator")

		d_vars = [var for var in tf.trainable_variables() if 'discriminator' in var.name]
		g_vars = [var for var in tf.trainable_variables() if 'generator' in var.name]
		
		self.sess = tf.Session()
		with tf.variable_scope("Optimizers"):
			self.D_optimizer = tf.train.AdamOptimizer(self.D_lr).minimize(self.d_loss, var_list = d_vars)
			self.G_optimizer = tf.train.AdamOptimizer(self.G_lr).minimize(self.g_loss, var_list = g_vars)
		self.init = tf.global_variables_initializer()
		self.saver = tf.train.Saver(write_version=tf.train.SaverDef.V2)
		tf.summary.scalar('Discriminator loss: ', self.d_loss)
		tf.summary.scalar('Generator loss', self.g_loss)
		tf.summary.scalar('Discriminator Learning Rate', self.D_lr)
		tf.summary.scalar('Generator Learning Rate', self.G_lr)
		tf.summary.image('Generated image', self.generated_imgs, max_outputs=4)
		self.summaries = tf.summary.merge_all()
		self.writer = tf.summary.FileWriter(self.opts.root_dir+self.opts.summary_dir, self.sess.graph)


	def plot_gradients_summary(self, name):
		if name == "Discriminator":
			d_vars = [var for var in tf.trainable_variables() if 'discriminator' in var.name]
			[tf.summary.histogram(name+'_grad'+'/{}'.format(var.name), tf.gradients(self.d_loss, var)) for var in d_vars]
		else:
			g_vars = [var for var in tf.trainable_variables() if 'generator' in var.name]
			[tf.summary.histogram(name+'_grad'+'/{}'.format(var.name), tf.gradients(self.g_loss, var)) for var in g_vars]


	def Discriminator(self, data, reuse=False):
		"""
		Discriminator part of GAN
		"""

		dims = self.opts.dims
		if self.opts.dataset == "CIFAR":
			with tf.variable_scope("discriminator"):
				conv1 = model.conv2d(data, [5,5,3,self.dims], 2, "conv1", is_training, False, reuse=reuse)
				conv2 = model.conv2d(conv1, [3,3,self.dims,self.dims*2], 2, "conv2", is_training, True, reuse=reuse, use_batch_norm=True)
				conv3 = model.conv2d(conv2, [3,3,self.dims*2,self.dims*4], 2, "conv3", is_training, True, reuse=reuse, use_batch_norm=True)
				full4 = model.fully_connected(tf.reshape(conv3, [self.opts.batch_size, -1]), self.opts.label_len, is_training, None, "full4", False, reuse=reuse)
				return full4
		else:
			with tf.variable_scope("discriminator"):
				conv1 = model.conv2d(data, [5, 5, self.c, dims], 2, "conv1", alpha=0.2, use_leak=True, bias_constant=0.01, reuse=reuse, use_batch_norm=False, is_training=self.is_training) # 14x14x64
				conv2 = model.conv2d(conv1, [5, 5, dims, dims * 2], 2, "conv2", alpha=0.2, use_leak=True, bias_constant=0.01, reuse=reuse, use_batch_norm=False, is_training=self.is_training) # 7x7x128
				# conv2_flat = tf.reshape(conv2, [-1, int(np.prod(conv2.get_shape()[1:]))])
				conv3 = model.conv2d(conv2, [3, 3, dims*2, dims * 4], 2, "conv3", alpha=0.2, use_leak=True, bias_constant=0.01, reuse=reuse, use_batch_norm=True, is_training=self.is_training) # 4x4x256
				full1 = model.fully_connected(tf.reshape(conv3, [-1, 4*4*dims*4]), dims*4*4*2, activation=tf.nn.relu, use_leak=True, name="full1", bias_constant=0.01, reuse=reuse, use_batch_norm=True, is_training=self.is_training) # 1
				full2 = model.fully_connected(full1, dims*4*4, activation=tf.nn.relu, name="full2", bias_constant=0.01, reuse=reuse, use_leak=True, use_batch_norm=True, is_training=self.is_training) # 1
				output = model.fully_connected(full2, self.opts.label_len, activation=None, name="output", bias_constant=0.01, reuse=reuse, use_leak=True, use_batch_norm=True, is_training=self.is_training) # 1

				# output = model.fully_connected(conv2_flat, 1, activation=None, use_leak=False, name="full1", bias_constant=0.01, reuse=reuse, use_batch_norm=False, is_training=self.is_training) # 1
				return output


	def Generator(self, code, reuse=False):
		"""
		Generator part of GAN
		"""

		dims = self.opts.dims
		if self.opts.dataset == "CIFAR":
			with tf.variable_scope("generator"):
				full1 = model.fully_connected(code, dims*4*4*4, is_training, tf.nn.relu, "full1", False, reuse=reuse, use_batch_norm=True)
				dconv2 = model.deconv(tf.reshape(full1, [-1, 4, 4, dims*4]), [8, 8, dims*2, dims*4], 2, "dconv2", is_training, False, reuse=reuse, use_batch_norm=True)
				dconv3 = model.deconv(dconv2, [16, 16, dims, dims*2], 2, "dconv3", is_training, False, reuse=reuse, use_batch_norm=True)
				dconv4 = model.deconv(dconv3, [32, 32, dims, 3], 2, "dconv4", is_training, False, reuse=reuse)
				return tf.nn.tanh(dconv4)
		else:
			with tf.variable_scope("generator"):
				full1 = model.fully_connected(code, 7*7*dims*2, is_training=self.is_training, activation=tf.nn.relu, name="full1", reuse=reuse, bias_constant=0.01, use_leak=True, use_batch_norm=True, initializer=tf.truncated_normal_initializer(stddev=0.2))
				full2 = model.fully_connected(full1, 4*4*dims*2, is_training=self.is_training, activation=tf.nn.relu, name="full2", reuse=reuse, bias_constant=0.01, use_leak=True, use_batch_norm=True, initializer=tf.truncated_normal_initializer(stddev=0.2))
				full3 = model.fully_connected(full2, 4*4*dims*4, is_training=self.is_training, activation=tf.nn.relu, name="full3", reuse=reuse, bias_constant=0.01, use_leak=True, use_batch_norm=True, initializer=tf.truncated_normal_initializer(stddev=0.2))
				dconv2 = model.deconv(tf.reshape(full3, [-1, 4, 4, dims*4]), [3,3,dims*2,dims*4], [self.opts.batch_size, 7, 7, dims*2], 2, "dconv2", tf.nn.relu, initializer=tf.truncated_normal_initializer(stddev=0.2),
									  bias_constant=0.0, reuse=reuse, use_batch_norm=True, is_training=self.is_training, use_leak=True)
				dconv3 = model.deconv(dconv2, [3,3,dims,dims*2], [self.opts.batch_size, 14, 14, dims], 2, "dconv3", tf.nn.relu, initializer=tf.truncated_normal_initializer(stddev=0.2),\
									  bias_constant=0.0, reuse=reuse, use_batch_norm=True, is_training=self.is_training, use_leak=True)
				dconv4 = model.deconv(dconv3, [3,3,1,dims], [self.opts.batch_size, 28, 28, 1], 2, "output", None, initializer=tf.truncated_normal_initializer(stddev=0.2),\
									  bias_constant=0.0, reuse=reuse)

				# full1_reshape = tf.reshape(full1, [-1, 7, 7, dims*2])
				# dconv2 = model.deconv(full1_reshape, [3,3,dims,dims*2], [self.opts.batch_size, 14, 14, dims], 2, "dconv2", activation=tf.nn.relu, initializer=tf.truncated_normal_initializer(stddev=0.2),
				# 					  bias_constant=0.0, reuse=reuse, use_batch_norm=True, is_training=self.is_training, use_leak=True)
				# dconv3 = model.deconv(dconv2, [3,3,1,dims], [self.opts.batch_size, 28, 28, 1], 2, "dconv3", activation=None, initializer=tf.truncated_normal_initializer(stddev=0.2),\
				# 					  bias_constant=0.0, reuse=reuse, use_batch_norm=False, is_training=self.is_training, use_leak=True)
				return tf.nn.sigmoid(dconv4)


	def loss(self):
		with tf.variable_scope("loss"):
			if not self.opts.use_labels:
				true_prob = tf.nn.sigmoid(self.true_logit)
				fake_prob = tf.nn.sigmoid(self.fake_logit)
			with tf.variable_scope("D_loss"):
				if self.opts.label_len > 1:
					d_true_loss = tf.nn.softmax_cross_entropy_with_logits(labels=self.labels, logits=self.true_logit, dim=1)
					d_fake_loss = tf.nn.softmax_cross_entropy_with_logits(labels=1-self.labels, logits=self.fake_logit, dim=1)
					d_loss = d_true_loss + d_fake_loss
				else:
					d_loss = tf.reduce_mean(-tf.log(true_prob)-tf.log(1-fake_prob))
			with tf.variable_scope("G_loss"):
				if self.opts.label_len > 1:
					g_loss = tf.nn.softmax_cross_entropy_with_logits(labels=self.labels, logits=self.fake_logit, dim=1)
				else:
					g_loss = tf.reduce_mean(-tf.log(fake_prob))
			return tf.reduce_mean(d_loss), tf.reduce_mean(g_loss)


	def train(self):
		code = np.random.uniform(low=-1.0, high=1.0, size=[self.opts.batch_size, self.opts.code_len]).astype(np.float32)
		utils = Dataset(self.opts)
		D_lr = self.opts.D_base_lr
		G_lr = self.opts.G_base_lr
		self.sess.run(self.init)
		for iteration in xrange(1, self.opts.MAX_iterations):
			batch_num = 0
			for batch_begin, batch_end in zip(xrange(0, self.opts.train_size, self.opts.batch_size), \
				xrange(self.opts.batch_size, self.opts.train_size, self.opts.batch_size)):
				begin_time = time.time()
				if self.opts.use_labels:
					batch_imgs, batch_labels = utils.load_batch(batch_begin, batch_end)
				else:
					batch_imgs = utils.load_batch(batch_begin, batch_end)
				noise = np.random.uniform(low=-1.0, high=1.0, size=[self.opts.batch_size, self.opts.code_len]).astype(np.float32)


				# Real data
				if self.opts.use_labels:
					feed_dict = {self.images:batch_imgs, self.D_lr:D_lr, self.G_lr:G_lr, self.code:noise, self.labels:batch_labels}
				else:
					feed_dict = {self.images:batch_imgs, self.D_lr:D_lr, self.G_lr:G_lr, self.code:noise}
				_, D_loss = self.sess.run([self.D_optimizer, self.d_loss], feed_dict=feed_dict)

				# Fake data
				if self.opts.use_labels:
					feed_dict = {self.images:batch_imgs, self.D_lr:D_lr, self.G_lr:G_lr, self.code:noise, self.labels:batch_labels}
				else:
					feed_dict = {self.images:batch_imgs, self.D_lr:D_lr, self.G_lr:G_lr, self.code:noise}
				_, G_loss, summary = self.sess.run([self.G_optimizer, self.g_loss, self.summaries], feed_dict=feed_dict)

				batch_num += 1
				self.writer.add_summary(summary, iteration * (self.opts.train_size/self.opts.batch_size) + batch_num)
				if batch_num % self.opts.display == 0:
					rem_time = (time.time() - begin_time) * (self.opts.MAX_iterations-iteration) * (self.opts.train_size/self.opts.batch_size)
					log  = '-'*20
					log += '\nIteration: {}/{}|'.format(iteration, self.opts.MAX_iterations)
					log += ' Batch Number: {}/{}|'.format(batch_num, self.opts.train_size/self.opts.batch_size)
					log += ' Batch Time: {}\n'.format(time.time() - begin_time)
					log += ' Remaining Time: {:0>8}\n'.format(datetime.timedelta(seconds=rem_time))
					log += ' D_lr: {} D_loss: {}\n'.format(D_lr, D_loss)
					log += ' G_lr: {} G_loss: {}\n'.format(G_lr, G_loss)
					print log
				if iteration % self.opts.lr_decay == 0 and batch_num == 1:
					D_lr *= self.opts.lr_decay_factor
					G_lr *= self.opts.lr_decay_factor
				if iteration % self.opts.ckpt_frq == 0 and batch_num == 1:
					self.saver.save(self.sess, self.opts.root_dir+self.opts.ckpt_dir+"{}_{}_{}_{}".format(iteration, D_lr, G_lr, D_loss+G_loss))
				if iteration % self.opts.generate_frq == 0 and batch_num == 1:
					feed_dict = {self.code: code}
					self.is_training = False
					imgs = self.sess.run(self.generated_imgs, feed_dict=feed_dict)
					if self.opts.dataset == "CIFAR":
						imgs = np.reshape(imgs, (self.opts.test_size, 3, 32, 32)).transpose(0, 2, 3, 1)
					else:
						imgs = np.reshape(imgs, (self.opts.test_size, 28, 28))
					utils.save_batch_images(imgs, [self.opts.grid_h, self.opts.grid_w], str(iteration)+".jpg", True)
					self.is_training = True


class VAE(object):
	"""
	Variatinoal Autoencoder
	"""

	def __init__(self, opts, is_training):
		self.h = opts.image_size_h
		self.w = opts.image_size_w
		self.c = opts.channels
		self.images = tf.placeholder(tf.float32, [None, self.h, self.w, self.c], "images") # 32x32x3
		self.lr = tf.placeholder(tf.float32, [], "learning_rate")
		self.is_training = is_training
		self.opts = opts
		self.mean, self.std = self.encoder()

		unit_gauss = tf.random_normal([self.opts.batch_size, self.opts.encoder_vec_size])
		self.z = self.mean + self.std * unit_gauss
		self.generated_imgs = self.decoder(self.z)

		self.l1, self.l2 = self.loss()
		self.l = self.l1+self.l2

		self.sess = tf.Session()
		self.optimizer = tf.train.AdamOptimizer(self.lr).minimize(self.l)
		self.init = tf.global_variables_initializer()
		self.saver = tf.train.Saver(write_version=tf.train.SaverDef.V2)
		tf.summary.scalar('Encoder loss', self.l1)
		tf.summary.scalar('Decoder loss', self.l2)
		tf.summary.scalar('Total loss', self.l)
		tf.summary.scalar('Learning Rate', self.lr)
		tf.summary.image('Generated images', self.generated_imgs, max_outputs=20)
		self.summaries = tf.summary.merge_all()
		self.writer = tf.summary.FileWriter(os.path.join(self.opts.root_dir, self.opts.summary_dir), self.sess.graph)

	def encoder(self):
		"""
		Encoder to generate the `latent vector`
		"""

		dims = self.opts.dims
		code_len = self.opts.encoder_vec_size
		if self.opts.dataset == "CIFAR":
			with tf.variable_scope("encoder"):
				conv1 = model.conv2d(self.images, [3, 3, self.c, dims], 2, "conv1", alpha=0.01) # 16x16x64
				conv2 = model.conv2d(conv1, [3, 3, dims, dims*2], 2, "conv2", alpha=0.01) # 8x8x128
				conv3 = model.conv2d(conv2, [3, 3, dims * 2, dims * 4], 2, "conv3", alpha=0.01) # 4x4x256
				conv4 = model.conv2d(conv3, [3, 3, dims * 4, dims * 8], 2, "conv4", alpha=0.01) # 2x2x512
				self.conv3_flat_len = int(np.prod(conv4.get_shape()[1:]))
				conv3_flat = tf.reshape(conv4, [-1, self.conv3_flat_len])
				mean = model.fully_connected(conv3_flat, code_len, self.is_training, None, "full3_mean", use_leak=True, bias_constant=0.01) # 40
				stds = model.fully_connected(conv3_flat, code_len, self.is_training, None, "full3_stds", use_leak=True, bias_constant=0.01) # 40
		else:
			with tf.variable_scope("encoder"):
				dims = 16
				conv1 = model.conv2d(self.images, [3, 3, self.c, dims], 2, "conv1", alpha=0.2, use_leak=True, bias_constant=0.01) # 14x14x16
				conv2 = model.conv2d(conv1, [3, 3, dims, dims * 2], 2, "conv2", alpha=0.2, use_leak=True, bias_constant=0.01) # 7x7x32
				conv2d_flat = tf.reshape(conv2, [-1, 7*7*32])
				mean = model.fully_connected(conv2d_flat, code_len, self.is_training, None, "full3_mean", use_leak=True, bias_constant=0.01) # 40
				stds = model.fully_connected(conv2d_flat, code_len, self.is_training, None, "full3_stds", use_leak=True, bias_constant=0.01) # 40

		return mean, stds

	def decoder(self, z):
		"""
		Generate images from the `latent vector`
		"""

		dims = self.opts.dims
		if self.opts.dataset == "CIFAR":
			with tf.variable_scope("decoder"):
				full1 = model.fully_connected(z, self.conv3_flat_len, self.is_training, tf.nn.relu, "full1", use_leak=True, alpha=0.2) # 4x4x256
				dconv2 = model.deconv(tf.reshape(full1, [-1, 2, 2, dims*8]), [3,3,dims*4,dims*8], [self.opts.batch_size, 4, 4, dims*4], 2, "dconv2", tf.nn.relu, initializer=tf.truncated_normal_initializer(stddev=0.02), use_leak=True, alpha=0.2) # 8x8x128
				dconv3 = model.deconv(dconv2, [3,3,dims*2,dims*4], [self.opts.batch_size, 8, 8, dims*2], 2, "dconv3", tf.nn.relu, initializer=tf.truncated_normal_initializer(stddev=0.02), use_leak=True, alpha=0.2) # 16x16x64
				dconv4 = model.deconv(dconv3, [3,3,dims,dims*2], [self.opts.batch_size, 16, 16, dims], 2, "dconv4", tf.nn.relu, initializer=tf.truncated_normal_initializer(stddev=0.02), use_leak=True, alpha=0.2) # 16x16x64
				output = model.deconv(dconv4, [3,3,self.c,dims], [self.opts.batch_size, self.h, self.w, self.c], 2, "output", initializer=tf.truncated_normal_initializer(stddev=0.02), use_leak=True, alpha=0.2) # 32x32x3
				probs = tf.nn.sigmoid(output)
		else:
			with tf.variable_scope("decoder"):
				full1 = model.fully_connected(z, 7*7*32, self.is_training, tf.nn.relu, "full1")
				dconv2 = model.deconv(tf.reshape(full1, [-1, 7, 7, 32]), [3,3,16,32],\
									  [self.opts.batch_size, 14, 14, 16], 2, "dconv2", tf.nn.relu,\
									  initializer=tf.truncated_normal_initializer(stddev=0.02),\
									  bias_constant=0.01)
				output = model.deconv(dconv2, [3,3,1,16], [self.opts.batch_size, 28, 28, 1],\
									  2, "output", None, initializer=tf.truncated_normal_initializer(stddev=0.02),\
									  bias_constant=0.01)
				probs = tf.nn.sigmoid(output)

		return probs

	def loss(self):
		img_flat = tf.reshape(self.images, [-1, self.h*self.w*self.c])
		gen_flat = tf.reshape(self.generated_imgs, [-1, self.h*self.w*self.c])

		encoder_loss = 0.5 * tf.reduce_sum(tf.square(self.mean)+tf.square(self.std)-tf.log(tf.square(self.std))-1., 1)
		decoder_loss = -tf.reduce_sum(img_flat * tf.log(1e-8 + gen_flat) + (1-img_flat) * tf.log(1e-8 + 1 - gen_flat),1)
		
		encoder_loss = self.opts.D_lambda * tf.reduce_mean(encoder_loss)
		decoder_loss = self.opts.G_lambda * tf.reduce_mean(decoder_loss)
		return encoder_loss, decoder_loss

	def train(self):
		utils = Dataset(self.opts)
		lr = self.opts.base_lr
		self.sess.run(self.init)
		for iteration in xrange(1, self.opts.MAX_iterations):
			batch_num = 0
			for batch_begin, batch_end in zip(xrange(0, self.opts.train_size, self.opts.batch_size), \
				xrange(self.opts.batch_size, self.opts.train_size, self.opts.batch_size)):
				begin_time = time.time()
				batch_imgs = utils.load_batch(batch_begin, batch_end)
				feed_dict = {self.images:batch_imgs, self.lr:lr}
				_, l1, l2, summary = self.sess.run([self.optimizer, self.l1, self.l2, self.summaries], feed_dict=feed_dict)

				batch_num += 1
				self.writer.add_summary(summary, iteration * (self.opts.train_size/self.opts.batch_size) + batch_num)
				if batch_num % self.opts.display == 0:
					rem_time = (time.time() - begin_time) * self.opts.MAX_iterations * (self.opts.train_size/self.opts.batch_size)
					log  = '-'*20
					log += '\nIteration: {}/{}|'.format(iteration, self.opts.MAX_iterations)
					log += ' Batch Number: {}/{}|'.format(batch_num, self.opts.train_size/self.opts.batch_size)
					log += ' Batch Time: {}\n'.format(time.time() - begin_time)
					log += ' Remaining Time: {:0>8}\n'.format(datetime.timedelta(seconds=rem_time))
					log += ' Learning Rate: {}\n'.format(lr)
					log += ' Encoder Loss: {}\n'.format(l1)
					log += ' Decoder Loss: {}\n'.format(l2)
					print log
				if iteration % self.opts.lr_decay == 0 and batch_num == 1:
					lr *= self.opts.lr_decay_factor
				if iteration % self.opts.ckpt_frq == 0 and batch_num == 1:
					self.saver.save(self.sess, os.path.join(self.opts.root_dir, self.opts.ckpt_dir, "{}".format(iteration)))
				if iteration % self.opts.generate_frq == 0 and batch_num == 1:
					generate_imgs = utils.test_images
					imgs = self.sess.run(self.generated_imgs, feed_dict={self.images:generate_imgs, self.lr:lr})
					if self.opts.dataset == "CIFAR":
						imgs = np.reshape(imgs, (self.opts.test_size, 3, 32, 32)).transpose(0, 2, 3, 1)
					else:
						imgs = np.reshape(imgs, (self.opts.test_size, 28, 28))
					tf.summary.image('Generated image', imgs[0])
					utils.save_batch_images(imgs, [self.opts.grid_h, self.opts.grid_w], str(iteration)+".jpg", True)

	def test(self, image):
		latest_ckpt = tf.train.latest_checkpoint(self.opts.ckpt_dir)
		tf.saver.restore(self.sess, latest_ckpt)
